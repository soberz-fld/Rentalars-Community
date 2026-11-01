# SPDX-License-Identifier: GPL-3.0-or-later
"""Making, cancelling and sending documents (DOK-003 to DOK-008, DOK-010; to the accounting: DOK-011).

``create_document`` takes the next number of the kind's number range, puts
the content together (``documents.content``), renders the PDF
(``documents.pdf``), for an invoice also the XRechnung
(``documents.xrechnung``), and stores everything with a checksum. A preview
renders the same PDF with "draft" instead of a number and stores nothing.

An offer holds until a date or for a number of days – by default as many as
the template of the offer says – and shows every position or only the groups
with their sums (DOK-013, :func:`offer_valid_until`, ``content.only_groups``).

Whole projects and subprojects (PRJ-045, PRJ-046)
--------------------------------------------------
Billing happens at the whole project: offer, order confirmation and invoice
of a whole project contain all its parts that are not cancelled
(``documents.content``); a part gets none of them – :func:`check_can_make`
points to the whole project. Delivery notes and crew dispositions are made
per part, with the part's delivery address and crew. A valid invoice of the
whole project, or one a part still has from before it became a part, stops
a second one. Who may not read every part (PRJ-049) cannot make the whole
project's priced documents: they show every part.

Invoices switched off (DOK-014)
--------------------------------------
Whoever writes the invoices in another program switches off "make invoices
in Rentalars" (:func:`invoices_enabled`): then no invoice and no
cancellation is made here, the head of a project suggests none, and the
accounting interfaces are hidden. What was made before stays readable.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.i18n import document_language, for_documents, local_pattern
from rentalars.documents import content as builder
from rentalars.documents.models import (
    MAKEABLE,
    MAX_VALIDITY_DAYS,
    NUMBER_RANGE_OF,
    OFFER_VALIDITY_DAYS,
    AccountingSettings,
    Document,
    DocumentDetail,
    DocumentKind,
    DocumentTemplate,
    InvoiceFormat,
    TextBlock,
)
from rentalars.projects.models import Project

#: The texts a fresh installation starts with (DOK-005); changed in the administration.
DEFAULT_TEMPLATES = {
    # DOK-010: the same texts as documents 0002 gives existing installations; DOK-013: the validity of 0004.
    DocumentKind.OFFER: {
        "title": "Angebot",
        "introduction": "Gerne bieten wir Ihnen für das Projekt {project} „{project_name}“ im Zeitraum {period} "
        "Folgendes an. Dieses Angebot gilt bis zum {valid_until}.",
        "closing": "Wir freuen uns auf Ihren Auftrag.",
        "validity_days": OFFER_VALIDITY_DAYS,
    },
    DocumentKind.ORDER_CONFIRMATION: {
        "title": "Auftragsbestätigung",
        "introduction": "Vielen Dank für Ihren Auftrag. Wir bestätigen das Projekt {project} „{project_name}“ "
        "im Zeitraum {period} wie folgt:",
        "closing": "Wir freuen uns auf die Zusammenarbeit.",
    },
    DocumentKind.DELIVERY_NOTE: {
        "title": "Lieferschein",
        "introduction": "Für das Projekt {project} „{project_name}“ liefern wir:",
        "closing": "Ware vollständig und unbeschädigt erhalten:",
    },
    DocumentKind.INVOICE: {
        "title": "Rechnung",
        "introduction": "Für das Projekt {project} „{project_name}“ ({period}) berechnen wir:",
        "closing": "Bitte überweisen Sie den Betrag bis zum {due_date} unter Angabe der Rechnungsnummer.",
    },
    DocumentKind.CANCELLATION: {
        "title": "Stornorechnung",
        "introduction": "Hiermit stornieren wir die unten genannte Rechnung vollständig.",
        "closing": "",
    },
    DocumentKind.CREW_SHEET: {
        "title": "Crew-Disposition",
        "introduction": "Einsatzplan für das Projekt {project} „{project_name}“, {venue}.",
        "closing": "",
    },
}


#: UIX-029: the start texts of a company whose documents are English. Once created, a template is the company's
#: own text and stays as it is when the language of the documents changes.
DEFAULT_TEMPLATES_ENGLISH = {
    DocumentKind.OFFER: {
        "title": "Quotation",
        "introduction": "For the project {project} “{project_name}” from {period} we are pleased to offer the "
        "following. This offer is valid until {valid_until}.",
        "closing": "We look forward to your order.",
        "validity_days": OFFER_VALIDITY_DAYS,
    },
    DocumentKind.ORDER_CONFIRMATION: {
        "title": "Order confirmation",
        "introduction": "Thank you for your order. We confirm the project {project} “{project_name}” from {period} "
        "as follows:",
        "closing": "We look forward to working with you.",
    },
    DocumentKind.DELIVERY_NOTE: {
        "title": "Delivery note",
        "introduction": "For the project {project} “{project_name}” we deliver:",
        "closing": "Goods received complete and undamaged:",
    },
    DocumentKind.INVOICE: {
        "title": "Invoice",
        "introduction": "For the project {project} “{project_name}” ({period}) we invoice:",
        "closing": "Please transfer the amount by {due_date}, quoting the invoice number.",
    },
    DocumentKind.CANCELLATION: {
        "title": "Cancellation invoice",
        "introduction": "We hereby cancel the invoice named below in full.",
        "closing": "",
    },
    DocumentKind.CREW_SHEET: {
        "title": "Crew disposition",
        "introduction": "Deployment plan for the project {project} “{project_name}”, {venue}.",
        "closing": "",
    },
}


def template_for(kind: str) -> DocumentTemplate:
    """The template of a kind; created with the start texts on first use (DOK-005).

    UIX-029: the start texts are English when the company's documents are.
    """
    template = DocumentTemplate.objects.filter(kind=kind).first()
    if template is None:
        texts = DEFAULT_TEMPLATES_ENGLISH if document_language() == "en" else DEFAULT_TEMPLATES
        template = DocumentTemplate.objects.create(kind=kind, **texts[DocumentKind(kind)])
    return template


def text_blocks_for(kind: str) -> list[TextBlock]:
    """The active text blocks offered for a kind of document."""
    return [block for block in TextBlock.objects.filter(is_active=True) if block.fits(kind)]


def payment_terms(project: Project) -> int:
    """Days to pay: those of the customer, else those of the company (KND-006)."""
    from rentalars.core.models import CompanyProfile

    if project.customer_id and project.customer.payment_terms_days is not None:
        return project.customer.payment_terms_days
    return CompanyProfile.load().payment_terms_days


#: DOK-014: the kinds that are made only while invoices are made in Rentalars.
INVOICE_KINDS = frozenset({DocumentKind.INVOICE, DocumentKind.CANCELLATION})


def invoices_enabled() -> bool:
    """Whether invoices and cancellations are made in Rentalars (DOK-014).

    The setting "use Rentalars as accounting software" (``SystemSettings.invoices_enabled``,
    on by default). Switched off – the invoices are written in another
    program –, no invoice and no cancellation can be made: not on the tab
    "Documents", not through the API, and the head of a project no longer
    suggests one. Handing over to Lexware Office and the DATEV export are
    hidden and refused. Invoices made before stay with their projects and
    can be read, downloaded and sent; a project is closed without an
    invoice, as it always could be.
    """
    from rentalars.core.models import SystemSettings

    return SystemSettings.load().invoices_enabled


def invoices_off_message() -> str:
    """What a refused invoice, cancellation or handing over says when invoices are switched off (DOK-014)."""
    return _(
        "Invoices are not made in Rentalars: the setting “Use Rentalars as accounting software” is off "
        "(Settings → Company data and settings)."
    )


def check_invoices_enabled() -> None:
    """Refuse an invoice, a cancellation or a handing over to the accounting while invoices are off (DOK-014).

    Raises:
        ValidationError: The setting "use Rentalars as accounting software" is off.
    """
    if not invoices_enabled():
        raise ValidationError(invoices_off_message())


def makeable_kinds() -> list[DocumentKind]:
    """The kinds that can be made now, the offer first: without the invoice while invoices are off (DOK-014)."""
    if invoices_enabled():
        return list(MAKEABLE)
    return [kind for kind in MAKEABLE if kind not in INVOICE_KINDS]


def open_invoice(project: Project) -> Document | None:
    """The invoice of a project that is not cancelled, if there is one.

    DOK-016: also a monthly invoice of service cases that bills the case.
    """
    from rentalars.documents.invoice_reminders import invoices_of

    return invoices_of(project).order_by("-created_at").first()


def billed_ids(document: Document) -> set[int]:
    """DOK-016: the projects a document bills besides its own – a monthly invoice and its cancellation."""
    source = document.cancels if document.cancels_id else document
    return set(source.billed_projects.values_list("pk", flat=True)) - {document.project_id}


def may_open_billed(document: Document, *, rights: Any, user: Any, minimum: Any = None) -> bool:
    """Whether the user reaches every project a monthly invoice bills: to read its PDF, to edit to cancel it.

    The invoice shows every case of its statement (DOK-016); access to the case
    it belongs to alone does not open the others (AUT-016, as PRJ-049).
    """
    from rentalars.projects.access import ProjectAccess, access_of_many

    others = billed_ids(document)
    if not others:
        return True
    minimum = ProjectAccess.READ if minimum is None else minimum
    levels = access_of_many(rights, user, sorted(others))
    return all(levels.get(pk, ProjectAccess.NONE) >= minimum for pk in others)


#: The kinds that list the positions with prices (DOK-003, DOK-006, DOK-010).
PRICED_CONTENT_KINDS = frozenset({DocumentKind.OFFER, DocumentKind.ORDER_CONFIRMATION, DocumentKind.INVOICE})


def default_validity_days() -> int:
    """How many days a new offer holds: as set in the template of the offer (DOK-013), else 14 (DOK-010)."""
    days = template_for(DocumentKind.OFFER).validity_days
    return OFFER_VALIDITY_DAYS if days is None else days


def offer_valid_until(
    issued_on: datetime.date, valid_until: datetime.date | None = None, validity_days: int | None = None
) -> datetime.date:
    """Until when an offer holds (DOK-010, DOK-013).

    The validity can be given as a date or as a number of days after the
    date of the offer; given both, they must say the same. Given neither,
    the offer holds as many days as the template of the offer says
    (:func:`default_validity_days`).

    Example: an offer of 01.03.2027 with 14 days holds until 15.03.2027;
    "until 15.03.2027" is the same.

    Raises:
        ValidationError: The date lies before the date of the offer, the
            number of days is negative or too large, or date and days differ.
    """
    if validity_days is not None:
        if not 0 <= validity_days <= MAX_VALIDITY_DAYS:
            raise ValidationError(
                {
                    "validity_days": _("An offer is valid for 0 to %(days)d days.") % {"days": MAX_VALIDITY_DAYS},
                }
            )
        from_days = issued_on + datetime.timedelta(days=validity_days)
        if valid_until is not None and valid_until != from_days:
            raise ValidationError(
                {
                    "validity_days": _(
                        "%(days)d days after %(date)s is %(until)s, not %(valid_until)s. Give one of the two."
                    )
                    % {
                        "days": validity_days,
                        "date": f"{issued_on:{local_pattern('%d.%m.%Y')}}",
                        "until": f"{from_days:{local_pattern('%d.%m.%Y')}}",
                        "valid_until": f"{valid_until:{local_pattern('%d.%m.%Y')}}",
                    }
                }
            )
        return from_days
    if valid_until is None:
        return issued_on + datetime.timedelta(days=default_validity_days())
    if valid_until < issued_on:
        raise ValidationError({"valid_until": _("An offer cannot be valid only until before its own date.")})
    return valid_until


def check_detail(kind: str, detail: str | None) -> str:
    """The level of detail of a new document: an offer can show its groups only (DOK-013), the others all lines.

    Raises:
        ValidationError: An unknown level, or "groups" for another kind than an offer.
    """
    if not detail:
        return DocumentDetail.LINES
    if detail not in DocumentDetail.values:
        raise ValidationError({"detail": _("Unknown level of detail.")})
    if detail != DocumentDetail.LINES and kind != DocumentKind.OFFER:
        raise ValidationError({"detail": _("Only an offer can show its groups without their positions.")})
    return detail


def build_content(
    project: Project,
    kind: str,
    *,
    number: str,
    issued_on: datetime.date,
    text_block_ids: list[int] | None = None,
    packlist: Any = None,
    valid_until: datetime.date | None = None,
    validity_days: int | None = None,
    detail: str | None = None,
    print_product_descriptions: bool | None = None,
    billing: Any = None,
) -> builder.DocumentContent:
    """Put the content of a new document together (without storing anything).

    Args:
        project: The project.
        kind: One of :class:`DocumentKind`, not a cancellation.
        number: The number the document gets (empty or "draft" while it is not made).
        issued_on: The date of the document.
        text_block_ids: Text blocks to add (DOK-005).
        packlist: For a delivery note: one packlist instead of all.
        valid_until: For an offer: until when it holds (DOK-010).
        validity_days: For an offer: how many days after its date it holds,
            instead of or together with ``valid_until``; neither: the days of
            the template of the offer (DOK-013, :func:`offer_valid_until`).
        detail: For an offer: "lines" (all positions, the default) or
            "groups" – the groups with their sums only (DOK-013).
        print_product_descriptions: whether the
            description of each product is printed under its position;
            ``None``: as the template of the kind says (:func:`prints_descriptions`).
        billing: for an invoice, a :class:`~rentalars.documents.billing.Billing` – the advance, partial or
            final invoice and its amount; ``None``: the ordinary invoice of the whole project.

    Raises:
        ValidationError: A cancellation, a validity that does not fit, or
            a level of detail the kind does not have; the rules of the types of invoice
            (``documents.billing``).
    """
    detail = check_detail(kind, detail)
    if kind not in PRICED_CONTENT_KINDS and kind not in (DocumentKind.DELIVERY_NOTE, DocumentKind.CREW_SHEET):
        raise ValidationError(_("A cancellation is made from the invoice it cancels."))
    # The checks answer in the user's language, before the document's language takes over.
    offer_until = offer_valid_until(issued_on, valid_until, validity_days) if kind == DocumentKind.OFFER else None
    # UIX-029: the fixed texts of the document in the language of the company's documents.
    with for_documents():
        template = template_for(kind)
        if kind in PRICED_CONTENT_KINDS:
            content = builder.build_priced(project, kind, title=template.title, number=number, issued_on=issued_on)
        elif kind == DocumentKind.DELIVERY_NOTE:
            content = builder.build_delivery_note(
                project, title=template.title, number=number, issued_on=issued_on, packlist=packlist
            )
        else:
            content = builder.build_crew_sheet(project, title=template.title, number=number, issued_on=issued_on)
        if kind == DocumentKind.INVOICE:
            content.payment_terms_days = payment_terms(project)
            content.due_on = issued_on + datetime.timedelta(days=content.payment_terms_days)
        validity: int | None = None
        if kind == DocumentKind.OFFER:
            content.valid_until = offer_until
            validity = (content.valid_until - issued_on).days
            if detail == DocumentDetail.GROUPS:
                builder.only_groups(content)  # DOK-013: the sums stay those of the complete offer
        values = builder.placeholder_values(
            project,
            due_on=content.due_on,
            terms=content.payment_terms_days,
            valid_until=content.valid_until,
            validity_days=validity,
        )
        content.introduction = builder.fill(template.introduction, values)
        content.closing = builder.fill(template.closing, values)
        content.footer = template.footer
        # Product descriptions: the choice is made here, once, for every renderer – PDF, XRechnung, the
        # stored content. A line's own text is never dropped, only what comes from the product.
        wanted = (
            template.print_product_descriptions if print_product_descriptions is None else print_product_descriptions
        )
        if kind == DocumentKind.CREW_SHEET:
            wanted = False  # a crew disposition lists people, not products
        if wanted:
            content.print_product_descriptions = True
        else:
            builder.strip_descriptions(content)
        if text_block_ids:
            # Only blocks meant for this kind (DOK-005); a block for invoices never lands on a delivery note.
            blocks = {
                block.pk: block
                for block in TextBlock.objects.filter(pk__in=text_block_ids, is_active=True)
                if block.fits(kind)
            }
            content.text_blocks = [builder.fill(blocks[pk].text, values) for pk in text_block_ids if pk in blocks]
        if kind == DocumentKind.INVOICE and billing is not None and billing.type:
            from rentalars.documents import billing as billing_rules

            billing_rules.apply(project, content, billing)  # Advance, partial or final invoice
        elif kind == DocumentKind.INVOICE:
            from rentalars.documents import billing as billing_rules

            refusal = billing_rules.problems(project, "")
            if refusal:
                raise ValidationError(refusal)
        return content


def check_can_make(project: Project, kind: str, content: builder.DocumentContent | None = None) -> list[str]:
    """Reasons that stop a document from being made; empty if none.

    An invoice needs a customer, the data the electronic invoice requires,
    and no other invoice of the project that is still valid – for a whole
    project, of none of its parts either (PRJ-046). Offer, order
    confirmation and invoice are made on the whole project, never on a part
    (PRJ-045).
    """
    from rentalars.documents.xrechnung import missing_data

    problems: list[str] = []
    if kind in INVOICE_KINDS and not invoices_enabled():
        return [invoices_off_message()]  # DOK-014: nothing else matters
    refusal = part_problem(project, kind)
    if refusal:
        problems.append(refusal)
    if kind in PRICED_CONTENT_KINDS and not project.customer_id:
        problems.append(_("An internal project has no customer to address this document to."))
    if kind == DocumentKind.INVOICE:
        existing = open_invoice(project)
        if existing is not None:
            problems.append(
                _("Invoice %(number)s of this project is still valid. Cancel it first.") % {"number": existing.number}
            )
        elif not project.parent_id:
            problems += _open_invoices_of_parts(project)
        if content is not None:
            missing = missing_data(content)
            if missing:
                problems.append(
                    _("For the electronic invoice, this is missing: %(items)s.") % {"items": ", ".join(missing)}
                )
    if kind == DocumentKind.CREW_SHEET and not project.crew_lines.exists():
        problems.append(_("Nobody is scheduled for this project yet."))
    return problems


def part_problem(project: Project, kind: str) -> str:
    """PRJ-045: offer, order confirmation and invoice of a part are those of its whole project; "" if allowed."""
    if kind not in PRICED_CONTENT_KINDS or not project.parent_id:
        return ""
    return _(
        "Offers, order confirmations and invoices are made on the whole project %(number)s – with all its subprojects."
    ) % {"number": project.parent.number}


def _open_invoices_of_parts(project: Project) -> list[str]:
    """PRJ-046: invoices the parts still have from before they became parts, and that are not cancelled.

    The invoice of the whole project charges the parts as well; it would
    charge them twice.
    """
    from rentalars.projects.family_prices import billed_parts

    parts, _cancelled = billed_parts(project)
    if not parts:
        return []
    invoices = Document.objects.filter(
        project__in=parts, kind=DocumentKind.INVOICE, cancelled_by__isnull=True
    ).select_related("project")
    return [
        _("Invoice %(number)s of subproject %(part)s is still valid. Cancel it first.")
        % {"number": invoice.number, "part": invoice.project.number}
        for invoice in invoices.order_by("project__number", "number")
    ]


def check_parts_readable(project: Project, kind: str, *, rights: Any, user: Any) -> None:
    """Refuse a whole project's priced document to someone who may not read all its parts (PRJ-049).

    The document lists every part that is not cancelled, with its prices.

    Raises:
        ValidationError: Names the parts the user may not read.
    """
    from rentalars.projects.access import ProjectAccess, access_level
    from rentalars.projects.family_prices import billed_parts

    if kind not in PRICED_CONTENT_KINDS or rights is None:
        return
    parts, _cancelled = billed_parts(project)
    hidden = [part.number for part in parts if access_level(rights, user, part) < ProjectAccess.READ]
    if hidden:
        raise ValidationError(
            _(
                "This document contains every subproject, and you may not read %(numbers)s. Ask somebody who may "
                "read all subprojects to make it."
            )
            % {"numbers": ", ".join(hidden)}
        )


def preview(
    project: Project,
    kind: str,
    *,
    text_block_ids: list[int] | None = None,
    packlist: Any = None,
    valid_until: datetime.date | None = None,
    validity_days: int | None = None,
    detail: str | None = None,
    print_product_descriptions: bool | None = None,
    rights: Any = None,
    user: Any = None,
    billing: Any = None,
) -> bytes:
    """The PDF as it would come out, marked as draft; nothing is stored or counted.

    The options are those of :func:`build_content`.

    Raises:
        ValidationError: A priced document of a part (PRJ-045), or – given
            ``rights`` – of a whole project with parts the user may not read
            (PRJ-049); options that do not fit (DOK-013).
    """
    from rentalars.documents.pdf import render_pdf

    if kind in INVOICE_KINDS:
        check_invoices_enabled()  # DOK-014: no draft of what cannot be made
    refusal = part_problem(project, kind)
    if refusal:
        raise ValidationError(refusal)
    check_parts_readable(project, kind, rights=rights, user=user)
    with for_documents():
        draft_number = _("DRAFT")
    content = build_content(
        project,
        kind,
        number=draft_number,
        issued_on=timezone.localdate(),
        text_block_ids=text_block_ids,
        packlist=packlist,
        valid_until=valid_until,
        validity_days=validity_days,
        detail=detail,
        print_product_descriptions=print_product_descriptions,
        billing=billing,
    )
    return render_pdf(content, template_for(kind), draft=True)


@transaction.atomic
def create_document(
    project: Project,
    kind: str,
    *,
    user: Any = None,
    text_block_ids: list[int] | None = None,
    packlist: Any = None,
    valid_until: datetime.date | None = None,
    validity_days: int | None = None,
    detail: str | None = None,
    print_product_descriptions: bool | None = None,
    rights: Any = None,
    billing: Any = None,
) -> Document:
    """Make a document and store it with the project for good (DOK-003 to DOK-007, DOK-010).

    An offer (DOK-010) may be made as often as wanted – each with its own
    number – and holds until ``valid_until`` or for ``validity_days``, by
    default as many days as the template of the offer says; it shows every
    position or – ``detail="groups"`` – the groups with their sums only
    (DOK-013). With ``rights``, the user must be able to read every part a
    whole project's priced document contains (PRJ-049). With
    ``print_product_descriptions`` the description of each product stands
    under its position – ``None`` takes the choice of the template of the
    kind; the choice is stored with the document. ``billing`` makes an advance, partial or final invoice
    (``documents.billing.Billing``).

    Raises:
        ValidationError: Something stops the document (see :func:`check_can_make`),
            an offer would expire before its own date, or the options do not fit.
    """
    from rentalars.core.models import NumberRange
    from rentalars.documents.pdf import render_pdf
    from rentalars.documents.xrechnung import build_xml

    if kind not in DocumentKind.values or kind == DocumentKind.CANCELLATION:
        raise ValidationError(_("Unknown kind of document."))
    if kind == DocumentKind.INVOICE:
        # DOK-016: the same lock as the monthly invoice of service cases takes on its cases.
        list(Project.objects.select_for_update().filter(pk=project.pk).values_list("pk"))
    problems = check_can_make(project, kind)
    if problems:
        raise ValidationError(problems)
    check_parts_readable(project, kind, rights=rights, user=user)
    issued_on = timezone.localdate()
    draft = build_content(
        project,
        kind,
        number="",
        issued_on=issued_on,
        text_block_ids=text_block_ids,
        packlist=packlist,
        valid_until=valid_until,
        validity_days=validity_days,
        detail=detail,
        print_product_descriptions=print_product_descriptions,
        billing=billing,
    )
    problems = check_can_make(project, kind, draft)
    if problems:
        raise ValidationError(problems)
    _value, number = NumberRange.allocate(NUMBER_RANGE_OF[DocumentKind(kind)])
    draft.number = number
    document = _store(project, draft, template_for(kind), user=user, render=render_pdf, xml=build_xml)
    _to_accounting(document, user)
    return document


def _to_accounting(document: Document, user: Any) -> None:
    """DOK-011: an invoice or cancellation goes to Lexware Office at once when the settings say so."""
    from rentalars.documents.lexware import transfer_automatically

    transfer_automatically(document, user=user)


def _store(
    project: Project | None,
    content: builder.DocumentContent,
    template: DocumentTemplate,
    *,
    user: Any,
    render: Any,
    xml: Any,
    customer: Any = None,
) -> Document:
    """Render and store a document for good (DOK-007).

    Free outgoing documents: without a project the document belongs
    to ``customer`` and the event is noted in the history of the customer.
    """
    structured = content.kind in {DocumentKind.INVOICE, DocumentKind.CANCELLATION}
    settings_row = AccountingSettings.load()
    # DOK-049: the format of the invoice – XRechnung (PDF and UBL apart) or ZUGFeRD (one PDF/A-3 with the CII)
    zugferd = structured and settings_row.invoice_format == InvoiceFormat.ZUGFERD
    with for_documents():  # UIX-029
        if zugferd:
            from rentalars.documents.cii import build_cii
            from rentalars.documents.zugferd import render_hybrid

            xml_bytes = build_cii(content)
            pdf = render_hybrid(content, template, xml_bytes)
        else:
            pdf = render(content, template, draft=False)
            xml_bytes = xml(content) if structured else None
    report = None
    if structured and xml_bytes:
        # DOK-042: the check against the rules; by default findings are only kept, the setting can stop the invoice
        from rentalars.documents import einvoice_rules

        report = einvoice_rules.check(xml_bytes)
        if settings_row.einvoice_blocks and report.errors:
            raise ValidationError(
                [_("The e-invoice breaks rules: ")]
                + [f"{finding.rule}: {finding.message}" for finding in report.errors[:10]]
            )
    document = Document(
        project=project,
        customer=customer,
        reference=content.reference,
        print_product_descriptions=content.print_product_descriptions,
        billing_type=content.billing_type if content.kind in {DocumentKind.INVOICE, DocumentKind.CANCELLATION} else "",
        billing_number=content.billing_number,
        kind=content.kind,
        number=content.number,
        title=content.title,
        issued_on=content.issued_on,
        created_by=user,
        content=content.as_json(),
        # A final invoice stands in the lists and sums with what it adds (the advances are in their own rows)
        net_total=(content.booked_net_total if content.deductions else content.net_total) if content.sections else None,
        gross_total=(content.booked_gross_total if content.deductions else content.gross_total)
        if content.sections
        else None,
        due_on=content.due_on,
        valid_until=content.valid_until,
        detail=content.detail,
        sha256=hashlib.sha256(pdf).hexdigest(),
        einvoice_format=(InvoiceFormat.ZUGFERD if zugferd else InvoiceFormat.XRECHNUNG) if structured else "",
    )
    document.file.save(f"{content.number}.pdf", ContentFile(pdf), save=False)
    if structured:
        document.xml_file.save(f"{content.number}.xml", ContentFile(xml_bytes), save=False)
    document.save()
    if report is not None:
        from rentalars.documents.einvoice_check import store_report

        store_report(document, report)
    record_event(
        project or customer, "document.created", {"kind": document.get_kind_display(), "number": document.number}
    )
    return document


@transaction.atomic
def cancel_invoice(invoice: Document, *, user: Any = None) -> Document:
    """Cancel an invoice by a cancellation with the negated amounts (DOK-006, DOK-007).

    DOK-014: while invoices are switched off, no cancellation is made either;
    a wrong invoice made before is corrected where the invoices are written now.

    Raises:
        ValidationError: Not an invoice, cancelled already, or invoices are switched off.
    """
    from rentalars.core.models import NumberRange
    from rentalars.documents.pdf import render_pdf
    from rentalars.documents.xrechnung import build_xml, missing_data

    check_invoices_enabled()
    from rentalars.documents import billing

    billing.lock_project_of(invoice)  # The project first, as when an invoice is made
    invoice = Document.objects.select_for_update().get(pk=invoice.pk)
    if invoice.kind != DocumentKind.INVOICE:
        raise ValidationError(_("Only invoices are cancelled."))
    if invoice.cancelled_by_id:
        raise ValidationError(_("This invoice is already cancelled."))
    if invoice.is_historic:  # Legacy import: it belongs to the old system; its credit note is written there
        raise ValidationError(_("An invoice taken over from an old system cannot be cancelled here."))
    final = billing.final_deducting(invoice)
    if final is not None:  # The final invoice deducts it – cancel that one first
        raise ValidationError(
            _("The final invoice %(number)s deducts this invoice. Cancel the final invoice first.")
            % {"number": final.number}
        )
    if invoice.partial_credits.exists():
        # Partly credited – cancel what is left, so that invoice, credits and cancellation add up to nothing
        return billing.credit_invoice(invoice, remainder=True, user=user)
    template = template_for(DocumentKind.CANCELLATION)
    original = builder.from_json(invoice.content)
    with for_documents():  # UIX-029
        content = builder.negated(original, title=template.title, number="", issued_on=timezone.localdate())
    # The cancellation is a document of today: it names the company as it is now.
    content.company = builder.company_data()
    missing = missing_data(content)
    if missing:
        raise ValidationError(
            _("For the electronic invoice, this is missing: %(items)s.") % {"items": ", ".join(missing)}
        )
    _value, content.number = NumberRange.allocate(NUMBER_RANGE_OF[DocumentKind.CANCELLATION])
    with for_documents():  # UIX-029
        if invoice.project_id is None:
            values = builder.free_placeholder_values(invoice.customer)  # A free invoice has no project
        else:
            values = builder.placeholder_values(invoice.project)
    content.introduction = builder.fill(template.introduction, values)
    content.closing = builder.fill(template.closing, values)
    content.footer = template.footer
    content.text_blocks = []
    cancellation = _store(
        invoice.project, content, template, user=user, render=render_pdf, xml=build_xml, customer=invoice.customer
    )
    Document.objects.filter(pk=cancellation.pk).update(cancels=invoice)
    invoice.cancelled_by = cancellation
    invoice.save(update_fields=["cancelled_by"])
    record_event(
        invoice.project or invoice.customer,
        "document.cancelled",
        {"kind": invoice.get_kind_display(), "number": invoice.number, "cancellation": cancellation.number},
    )
    # DOK-016: a monthly invoice of service cases – its statement is a draft again, its cases are open.
    from rentalars.documents.statements import invoice_cancelled

    invoice_cancelled(invoice, cancellation, user=user)
    cancellation.refresh_from_db()
    _to_accounting(cancellation, user)
    return cancellation


def mark_sent(document: Document, to: str) -> None:
    """Note that a document went out by mail (DOK-008)."""
    document.sent_at = timezone.now()
    document.sent_to = to[:500]
    document.save(update_fields=["sent_at", "sent_to"])
    record_event(
        document.project or document.customer,
        "document.sent",
        {"kind": document.get_kind_display(), "number": document.number, "to": to[:200]},
    )


def verify(document: Document) -> bool:
    """Whether the stored PDF is still the one that was made (DOK-007)."""
    with document.file.open("rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest() == document.sha256
