# SPDX-License-Identifier: GPL-3.0-or-later
"""Documents for the customer and the crew, stored unchangeably with the project (chapter 5.10).

These kinds of documents are made from a project (DOK-003, DOK-004, DOK-006, DOK-010):

==========================  ===================================================
offer                       the positions with prices, before the order; valid
                            until a date; with the optional parts (DOK-010);
                            on request only the groups with their sums (DOK-013)
order confirmation          the positions with prices, as agreed
delivery note               what goes to the customer, without prices
invoice                     the positions with prices, taxes, payment terms; with
                            a structured electronic invoice (XRechnung, UBL)
cancellation                cancels an invoice; it never disappears
crew disposition            who works when and where as what, with the contact
                            data people released – never a rate (PER-019)
==========================  ===================================================

A document, once made, is never changed (DOK-007): its PDF and the content it
was made from are stored, with a checksum. A wrong invoice is cancelled by a
cancellation and a new invoice, as the law wants it.

The look of each kind – heading, introduction, closing text, footer – comes
from a :class:`DocumentTemplate`; reusable paragraphs from
:class:`TextBlock` (DOK-005). Logo and company data come from the company
profile, the numbers from the number ranges (ADM-003).

Invoices and cancellations go to the accounting (DOK-011, DOK-012): how is
set in :class:`AccountingSettings`; what was handed to Lexware Office is
noted in a :class:`LexwareTransfer` per document.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.models import SingletonModel
from rentalars.core.payment_base import PaymentBase


class DocumentKind(models.TextChoices):
    """The kinds of documents (DOK-003, DOK-004, DOK-006, DOK-010), in the order a project needs them."""

    OFFER = "offer", _("offer")
    ORDER_CONFIRMATION = "order_confirmation", _("order confirmation")
    DELIVERY_NOTE = "delivery_note", _("delivery note")
    INVOICE = "invoice", _("invoice")
    CANCELLATION = "cancellation", _("cancellation")
    CREW_SHEET = "crew_sheet", _("crew disposition")


class BillingType(models.TextChoices):
    """Which part of a project an invoice bills – empty for the ordinary invoice of the whole project.

    * ``advance`` – Abschlagsrechnung: a payment on account; deducted from the final invoice.
    * ``partial`` – Teilrechnung: a part of the project billed on its own; deducted from the final invoice as well.
    * ``final`` – Schlussrechnung: the whole project, with the advance and partial invoices deducted.
    * ``credit`` – Teilgutschrift: a part of an invoice credited (the document is of the kind cancellation).
    """

    ADVANCE = "advance", _("advance invoice")
    PARTIAL = "partial", _("partial invoice")
    FINAL = "final", _("final invoice")
    CREDIT = "credit", _("partial credit note")


#: The types that bill a part: the project is not invoiced by them alone.
PART_BILLING = frozenset({BillingType.ADVANCE, BillingType.PARTIAL})

#: Kinds that show prices: only for people with the price right (AUT-019).
PRICED_KINDS = frozenset(
    {DocumentKind.OFFER, DocumentKind.ORDER_CONFIRMATION, DocumentKind.INVOICE, DocumentKind.CANCELLATION}
)

#: The kinds that can be made in the browser, the offer first (DOK-010); a cancellation is made from its invoice.
MAKEABLE = [kind for kind in DocumentKind if kind != DocumentKind.CANCELLATION]

#: DOK-010: how long an offer is valid unless the person making it says otherwise. DOK-013: the start
#: value of :attr:`DocumentTemplate.validity_days` of the offer, which the settings change.
OFFER_VALIDITY_DAYS = 14

#: DOK-013: the longest validity of an offer, in days – ten years.
MAX_VALIDITY_DAYS = 3650


class DocumentDetail(models.TextChoices):
    """How much of the planning an offer shows (DOK-013); the same words as the price overview (PRJ-036).

    ``groups``: every group with its description and its sum, without the
    lines that make up the sum. Lines outside every group, the personnel and
    the surcharges are listed as with ``lines``; so are optional and
    alternative lines in a group – they are not part of its sum, so the sum
    cannot stand for them. The totals are the same either way.
    """

    LINES = "lines", _("with positions")
    GROUPS = "groups", _("only groups")


#: The number range of each kind (ADM-003, DOK-005).
NUMBER_RANGE_OF = {
    DocumentKind.OFFER: "offer",
    DocumentKind.ORDER_CONFIRMATION: "order_confirmation",
    DocumentKind.DELIVERY_NOTE: "delivery_note",
    DocumentKind.INVOICE: "invoice",
    DocumentKind.CANCELLATION: "invoice",
    DocumentKind.CREW_SHEET: "crew_sheet",
}


class DocumentTemplate(AuditedModel):
    """Heading and texts of one kind of document (DOK-005).

    DOK-018: changes are written to the change log – in the
    administration and when the default texts of a language are taken over
    (``documents.template_texts``).

    Texts may contain placeholders that are filled when the document is
    made: ``{project}``, ``{project_name}``, ``{customer}``, ``{period}``,
    ``{venue}``, ``{due_date}``, ``{payment_terms}``, and for an offer
    ``{valid_until}`` (DOK-010) and ``{validity_days}`` (DOK-013).

    DOK-013: the template of the offer also says how many days a new offer
    is valid (``validity_days``); the other kinds have none.
    """

    kind = models.CharField(_("kind"), max_length=20, choices=DocumentKind.choices, unique=True)
    title = models.CharField(_("heading"), max_length=80)
    introduction = models.TextField(_("introduction"), blank=True)
    closing = models.TextField(_("closing text"), blank=True)
    footer = models.TextField(
        _("additional footer"), blank=True, help_text=_("Printed below address, bank and register details.")
    )
    show_logo = models.BooleanField(_("print the logo"), default=True)
    #: Product descriptions; DOK-021: whether new documents of this kind print the description of the products
    #: under their positions. Off at first. Chosen again for each document.
    print_product_descriptions = models.BooleanField(
        _("print the description of the products"),
        default=False,
        help_text=_(
            "The description of a product is printed under its position. A new document starts with this choice; "
            "it can be changed when the document is made."
        ),
    )
    #: Free outgoing documents: the introduction of a document made without a project, where the
    #: introduction above would speak of a project. Empty: the standard text of the kind.
    free_introduction = models.TextField(
        _("introduction without project"),
        blank=True,
        help_text=_(
            "For documents made in Accounting without a project. Empty: a standard text. Placeholders: {customer}, "
            "{due_date}, {payment_terms}, {valid_until}."
        ),
    )
    #: DOK-013: offers only – the validity a new offer starts with.
    validity_days = models.PositiveSmallIntegerField(
        _("validity in days"),
        null=True,
        blank=True,
        validators=[MaxValueValidator(MAX_VALIDITY_DAYS)],
        help_text=_("How many days a new offer is valid; it can be changed when the offer is made."),
    )

    class Meta:
        verbose_name = _("document template")
        verbose_name_plural = _("document templates")
        ordering = ["kind"]

    def __str__(self) -> str:
        return self.get_kind_display()

    def clean(self) -> None:
        """DOK-013: the offer has a validity in days, the other kinds have none."""
        super().clean()
        if self.kind == DocumentKind.OFFER and self.validity_days is None:
            raise ValidationError({"validity_days": _("Enter how many days a new offer is valid.")})
        if self.kind != DocumentKind.OFFER and self.validity_days is not None:
            raise ValidationError({"validity_days": _("Only an offer has a validity.")})


def text_block_kinds() -> list[tuple[str, str]]:
    """The kinds a text block can be offered for; a cancellation takes over its invoice and gets none."""
    return [(value, label) for value, label in DocumentKind.choices if value != DocumentKind.CANCELLATION]


class TextBlock(models.Model):
    """A paragraph that can be added to a document when it is made, e.g. terms of rental (DOK-005)."""

    name = models.CharField(_("name"), max_length=120, unique=True)
    text = models.TextField(_("text"))
    kinds = models.JSONField(
        _("for"), default=list, blank=True, help_text=_("The kinds of documents it is offered for; empty: all.")
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("text block")
        verbose_name_plural = _("text blocks")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def fits(self, kind: str) -> bool:
        """Whether the block is offered for this kind of document."""
        return not self.kinds or kind in self.kinds


def document_file_path(instance: Document, filename: str) -> str:
    """Store documents per project under their number (DOK-007); those without a project under ``free``.

    Free outgoing documents: a document of Buchhaltung has no project.
    """
    import re

    safe = re.sub(r"[^A-Za-z0-9-]", "_", instance.number)
    folder = instance.project_id if instance.project_id else "free"
    return f"documents/{folder}/{safe}{filename[filename.rfind('.') :]}"


class Document(models.Model):
    """A document made from a project; never changed afterwards (DOK-007).

    ``content`` holds what the PDF shows – positions, totals, addresses –
    as it was when the document was made. ``sha256`` is the checksum of the
    stored PDF. Only the notes about sending and cancelling change later.
    """

    #: Fields that may change after the document was made.
    MUTABLE_FIELDS: ClassVar[frozenset[str]] = frozenset({"sent_at", "sent_to", "cancelled_by"})

    #: Free outgoing documents: empty for a document made in Accounting without a project.
    project = models.ForeignKey(
        "projects.Project",
        verbose_name=_("project"),
        on_delete=models.PROTECT,
        related_name="documents",
        null=True,
        blank=True,
    )
    #: The customer the document was made for – that of the project when it was made, or the one chosen
    #: for a free document. Set when the row is written (see :meth:`save`); empty for an internal project.
    customer = models.ForeignKey(
        "customers.Customer",
        verbose_name=_("customer"),
        on_delete=models.PROTECT,
        related_name="outgoing_documents",
        null=True,
        blank=True,
    )
    kind = models.CharField(_("kind"), max_length=20, choices=DocumentKind.choices)
    number = models.CharField(_("number"), max_length=40, unique=True)
    title = models.CharField(_("title"), max_length=120)
    issued_on = models.DateField(_("date"))
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    content = models.JSONField(_("content"), default=dict)
    net_total = models.DecimalField(_("net"), max_digits=12, decimal_places=2, null=True, blank=True)
    gross_total = models.DecimalField(_("gross"), max_digits=12, decimal_places=2, null=True, blank=True)
    due_on = models.DateField(_("due on"), null=True, blank=True)
    #: DOK-010: until when an offer holds.
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    #: DOK-013: an offer with all positions, or with the groups and their sums only.
    detail = models.CharField(
        _("level of detail"), max_length=10, choices=DocumentDetail.choices, default=DocumentDetail.LINES
    )
    file = models.FileField(_("PDF"), upload_to=document_file_path, max_length=200)
    sha256 = models.CharField(_("checksum"), max_length=64)
    #: DOK-006: the structured electronic invoice (XRechnung, UBL).
    xml_file = models.FileField(_("XRechnung"), upload_to=document_file_path, max_length=200, blank=True)
    #: DOK-049: the format of the structured invoice at the time of making – "xrechnung" (PDF and UBL apart)
    #: or "zugferd" (the PDF is a PDF/A-3 with the CII inside; ``xml_file`` holds the same CII). Empty for documents
    #: that have none and for older ones (see :attr:`einvoice_syntax`).
    einvoice_format = models.CharField(_("format of the e-invoice"), max_length=10, blank=True, default="")
    #: A cancellation names the invoice it cancels; the invoice names its cancellation.
    cancels = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="cancellation")
    cancelled_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    sent_at = models.DateTimeField(_("sent"), null=True, blank=True)
    sent_to = models.CharField(_("sent to"), max_length=500, blank=True)
    #: Free outgoing documents: the subject line of a document without a project ("Referenz").
    reference = models.CharField(_("reference"), max_length=200, blank=True)
    #: Product descriptions; DOK-021: whether the description of the products was printed under the positions.
    #: Chosen when the document was made; the stored content holds exactly what was printed.
    print_product_descriptions = models.BooleanField(_("description of the products printed"), default=False)
    #: DOK-016: the projects an invoice bills – a monthly invoice of service cases bills every case of its
    #: statement (``documents.statements``); ``project`` is the first of them. Empty for an invoice of one project.
    #: Set once when the invoice is made; a many-to-many field is no column of the document, which stays unchanged.
    billed_projects = models.ManyToManyField(
        "projects.Project", verbose_name=_("projects billed"), related_name="billed_documents", blank=True
    )

    #: Several invoices per project: empty for the ordinary invoice; see :class:`BillingType`.
    billing_type = models.CharField(
        _("type of invoice"), max_length=10, choices=BillingType.choices, blank=True, default=""
    )
    #: The running number among the advance and partial invoices of the project ("2. Abschlagsrechnung").
    billing_number = models.PositiveSmallIntegerField(_("number in the project"), null=True, blank=True)
    #: A partial credit note names the invoice it credits (a cancellation uses ``cancels``, which is one-to-one).
    credit_for = models.ForeignKey(
        "self",
        verbose_name=_("credits invoice"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="partial_credits",
    )

    class Meta:
        verbose_name = _("document")
        verbose_name_plural = _("documents")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.title} {self.number}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """A document is written once; afterwards only sending and cancelling are noted (DOK-007)."""
        if self.pk is not None:
            fields = kwargs.get("update_fields")
            if fields is None or not set(fields) <= self.MUTABLE_FIELDS:
                raise ValidationError(_("Documents cannot be changed. Cancel an invoice and make a new one."))
        elif self.customer_id is None and self.project_id is not None:
            # The customer is kept with the document, so that lists need no project to name it.
            self.customer_id = self.project.customer_id
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        """Documents stay (DOK-007)."""
        raise ValidationError(_("Documents cannot be deleted."))

    @property
    def einvoice_syntax(self) -> str:
        """One of "xrechnung", "zugferd" or "" – documents that have an XML are XRechnung."""
        return self.einvoice_format or ("xrechnung" if self.xml_file else "")

    @property
    def is_free(self) -> bool:
        """Free outgoing documents: whether the document was made without a project, in Accounting."""
        return self.project_id is None

    @property
    def is_priced(self) -> bool:
        """Whether the document shows prices (AUT-019)."""
        return self.kind in PRICED_KINDS

    @property
    def is_cancelled(self) -> bool:
        """Whether this invoice was cancelled."""
        return self.cancelled_by_id is not None

    @property
    def validity_days(self) -> int | None:
        """DOK-013: how many days after its date an offer holds; ``None`` for other documents."""
        if self.valid_until is None or self.issued_on is None:
            return None
        return (self.valid_until - self.issued_on).days

    @property
    def file_name(self) -> str:
        """The name under which the PDF is downloaded or sent."""
        return f"{self.title}-{self.number}.pdf".replace(" ", "-")

    @property
    def is_historic(self) -> bool:
        """Legacy import: whether this invoice was taken over from an old system (``projects.legacy_import``).

        Such an invoice is a record of what happened before Rentalars: it was booked in the old system, is not handed to
        the accounting and not cancelled here.
        """
        return self.pk is not None and hasattr(self, "legacy_item")

    @property
    def is_bookable(self) -> bool:
        """Whether the document goes to the accounting: invoices and cancellations (DOK-011, DOK-012).

        An invoice taken over from an old system (:attr:`is_historic`) does not: it was booked there.
        """
        return self.kind in BOOKABLE_KINDS and not self.is_historic


# --- Outgoing documents without a project ------------------------------------------------

#: Free outgoing documents: the kinds that make sense without a project – the ones with prices a customer
#: is offered, confirmed or billed. A delivery note needs the packlists of a project, a crew disposition its crew;
#: a cancellation is made from its invoice (also a free one).
FREE_KINDS: tuple[str, ...] = (DocumentKind.OFFER, DocumentKind.ORDER_CONFIRMATION, DocumentKind.INVOICE)


class DocumentDraft(AuditedModel):
    """The draft of an outgoing document made in Accounting without a project (free outgoing documents; DOK-022).

    A document is never changed once it exists (DOK-007), so the lines are
    edited here, in a draft, until "Ausstellen" turns it into a
    :class:`Document` (``documents.free``): the number is taken from the
    range of the kind only then – the ranges stay gapless and are shared
    with the documents of projects –, the PDF is made and the draft is gone.
    The way is that of the monthly statement (:class:`MonthlyStatement`).

    ``introduction`` and ``closing`` hold the texts with their placeholders
    (``{customer}``, ``{due_date}``, …) as they will be filled in when the
    document is issued. Empty ``issued_on`` means the day of issuing.
    """

    kind = models.CharField(_("kind"), max_length=20, choices=[(kind, DocumentKind(kind).label) for kind in FREE_KINDS])
    customer = models.ForeignKey(
        "customers.Customer", verbose_name=_("customer"), on_delete=models.PROTECT, related_name="document_drafts"
    )
    billing_address = models.ForeignKey(
        "customers.CustomerAddress",
        verbose_name=_("billing address"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("Empty: the address of the customer."),
    )
    contact = models.ForeignKey(
        "customers.Contact",
        verbose_name=_("contact"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    issued_on = models.DateField(
        _("date"), null=True, blank=True, help_text=_("Empty: the day the document is issued.")
    )
    payment_terms_days = models.PositiveSmallIntegerField(
        _("payment terms in days"),
        null=True,
        blank=True,
        validators=[MaxValueValidator(365)],
        help_text=_("Invoices only. Empty: as for the customer, else as in the company settings."),
    )
    valid_until = models.DateField(
        _("valid until"), null=True, blank=True, help_text=_("Offers only. Empty: as many days as the template says.")
    )
    service_start = models.DateField(
        _("service from"), null=True, blank=True, help_text=_("Empty: the service is dated like the document.")
    )
    service_end = models.DateField(_("service until"), null=True, blank=True)
    reference = models.CharField(
        _("reference"), max_length=200, blank=True, help_text=_("Printed as subject line, e.g. “Hire of a PA system”.")
    )
    introduction = models.TextField(_("introduction"), blank=True)
    closing = models.TextField(_("closing text"), blank=True)
    text_block_ids = models.JSONField(_("text blocks"), default=list, blank=True)
    print_product_descriptions = models.BooleanField(_("print the description of the products"), default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    changed_at = models.DateTimeField(_("changed"), default=timezone.now, editable=False)

    audit_exclude = frozenset({"changed_at", "text_block_ids"})

    class Meta:
        verbose_name = _("draft of an outgoing document")
        verbose_name_plural = _("drafts of outgoing documents")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{DocumentKind(self.kind).label} {self.customer}"

    def audit_parent(self) -> models.Model | None:
        """The draft shows in the history of its customer."""
        return self.customer


class DraftLine(AuditedModel):
    """One line of a:class:`DocumentDraft`: a free line or one taken from a product (free outgoing documents; DOK-022).

    ``title`` and ``note`` are the line's own text and always print. The
    description of a ``product`` is not copied: it is read when the document
    is issued and printed only if the document asks for the descriptions
    (``DocumentDraft.print_product_descriptions``). A line taken from a
    product starts with its title, unit, price and tax rate, which the line
    then owns (PRJ-015).
    """

    draft = models.ForeignKey(DocumentDraft, verbose_name=_("draft"), on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveIntegerField(_("position"), default=0)
    product = models.ForeignKey(
        "products.Product",
        verbose_name=_("product"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    title = models.CharField(_("title"), max_length=200)
    note = models.TextField(_("note"), blank=True, help_text=_("Printed under the title."))
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.ForeignKey(
        "masterdata.Unit", verbose_name=_("unit"), null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    unit_price = models.DecimalField(
        _("unit price (net)"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    tax_rate = models.ForeignKey(
        "masterdata.TaxRate", verbose_name=_("tax rate"), on_delete=models.PROTECT, related_name="+"
    )
    discount_percent = models.DecimalField(
        _("discount in percent"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    #: A line of text only – a heading or a remark between the positions: no quantity, price or tax is used.
    is_text = models.BooleanField(_("text line"), default=False)

    class Meta:
        verbose_name = _("line of a draft")
        verbose_name_plural = _("lines of a draft")
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.title

    def audit_parent(self) -> models.Model | None:
        """The line shows in the history of the customer of its draft."""
        return self.draft.customer


# --- Monthly statements of service cases (DOK-016) ----------------------------------------


class StatementStatus(models.TextChoices):
    """Where a monthly statement of service cases stands (DOK-016).

    A discarded draft is deleted – there is no status for it.
    """

    DRAFT = "draft", _("draft")
    #: The invoice was made in Rentalars (DOK-014 on).
    INVOICED = "invoiced", _("invoiced")
    #: "Als abgerechnet markiert": the invoice was written in another program (DOK-014 off).
    MARKED = "marked", _("marked as invoiced")


class MonthlyStatement(AuditedModel):
    """The statement of one customer's service cases of one month (DOK-016).

    Collected by ``documents.statements``: the cases done in the month or with
    approved times or expenses in it, each with its activity text and its
    positions (times by job function, expenses, free positions), all of it in
    ``content``. A draft is checked and changed, then becomes an invoice
    (``invoice``, made in Rentalars) or is marked as invoiced elsewhere.

    One draft per customer and month is made by "Entwurf anlegen"; an invoiced
    or marked statement may be followed by another one of the same month for
    cases that came later. A cancelled invoice makes its statement a draft
    again. Changes of the content are not written to the change log – it is
    the draft of a document; status, cases and invoice are.
    """

    customer = models.ForeignKey(
        "customers.Customer",
        verbose_name=_("customer"),
        on_delete=models.PROTECT,
        related_name="monthly_statements",
    )
    #: The first day of the month.
    month = models.DateField(_("month"))
    status = models.CharField(
        _("status"), max_length=10, choices=StatementStatus.choices, default=StatementStatus.DRAFT
    )
    cases = models.ManyToManyField(
        "projects.Project", verbose_name=_("service cases"), related_name="monthly_statements", blank=True
    )
    #: Per case its activity text and positions, the introduction, what was removed – see ``documents.statements``.
    content = models.JSONField(_("content"), default=dict, blank=True)
    #: The invoice made of it; documents are never deleted, so it stays as long as the statement.
    invoice = models.ForeignKey(
        Document,
        verbose_name=_("invoice"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="monthly_statements",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    changed_at = models.DateTimeField(_("changed"), default=timezone.now, editable=False)
    marked_at = models.DateTimeField(_("marked as invoiced"), null=True, blank=True, editable=False)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    audit_exclude = frozenset({"content", "changed_at"})

    class Meta:
        verbose_name = _("monthly statement")
        verbose_name_plural = _("monthly statements")
        ordering = ["-month", "customer__name", "pk"]
        indexes = [models.Index(fields=["month", "status"], name="statement_month_status_idx")]

    def __str__(self) -> str:
        return f"{self.customer} {self.month:%m/%Y}"

    def audit_parent(self) -> models.Model | None:
        """The statement shows in the history of its customer."""
        return self.customer

    def clean(self) -> None:
        """The month is stored as its first day."""
        super().clean()
        if self.month and self.month.day != 1:
            raise ValidationError({"month": _("A month is stored as its first day.")})

    @property
    def is_draft(self) -> bool:
        """Whether the statement can still be changed."""
        return self.status == StatementStatus.DRAFT


class StatementClaim(models.Model):
    """A time or an expense a monthly statement bills (DOK-016).

    The catalogue's rule that every time and every
    expense is billed by at most one monthly statement is kept by the database: a time and an
    expense have one claim at most (``OneToOneField``), whatever case they
    belong to now. The claims follow the positions of the statement's content
    – also those removed by hand: it was decided not to charge them – and go
    with a draft that is deleted or a case taken out of it.
    """

    statement = models.ForeignKey(
        MonthlyStatement, verbose_name=_("monthly statement"), on_delete=models.CASCADE, related_name="claims"
    )
    time_entry = models.OneToOneField(
        "timetracking.TimeEntry",
        verbose_name=_("time entry"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="statement_claim",
    )
    expense = models.OneToOneField(
        "timetracking.Expense",
        verbose_name=_("expense"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="statement_claim",
    )

    class Meta:
        verbose_name = _("billed time or expense")
        verbose_name_plural = _("billed times and expenses")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(time_entry__isnull=False, expense__isnull=True)
                | models.Q(time_entry__isnull=True, expense__isnull=False),
                name="statement_claim_one_thing",
            )
        ]

    def __str__(self) -> str:
        return f"{self.statement_id}: {self.time_entry_id or self.expense_id}"


# --- Handing invoices to the accounting (DOK-011, DOK-012) ---------------------------------------

#: The kinds of documents the accounting gets.
BOOKABLE_KINDS = frozenset({DocumentKind.INVOICE, DocumentKind.CANCELLATION})


def rate_key(percent: Any) -> str:
    """A tax rate as key of the account mappings: 19.00 → "19", 7.50 → "7.5", 0 → "0"."""
    from decimal import Decimal

    text = f"{Decimal(str(percent)):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


class ChartOfAccounts(models.TextChoices):
    """The standard charts of accounts of DATEV (DOK-012)."""

    SKR03 = "SKR03", "SKR 03"
    SKR04 = "SKR04", "SKR 04"


#: DOK-012: revenue accounts per tax rate as the DATEV charts of accounts have them. 8400/4400 and
#: 8300/4300 are automatic accounts (19 % and 7 % output tax): DATEV books the tax itself, no tax key
#: is needed. For 0 % the account of services taxable in another EU country (reverse charge,
#: 8336/4336) is the usual case of a rental company; the tax adviser may want another one, e.g.
#: 8338/4338 for services to third countries.
DEFAULT_REVENUE_ACCOUNTS: dict[str, dict[str, str]] = {
    ChartOfAccounts.SKR03: {"19": "8400", "7": "8300", "0": "8336"},
    ChartOfAccounts.SKR04: {"19": "4400", "7": "4300", "0": "4336"},
}


class DebitorMode(models.TextChoices):
    """How the customers become accounts in the DATEV export (DOK-012)."""

    # UIX-029: "debtor", the English word for the "Debitor" of German accounting.
    PER_CUSTOMER = "per_customer", _("one debtor account per customer")
    COLLECTIVE = "collective", _("one collective debtor account")


#: DOK-011: the posting category "Einnahmen" of Lexware Office – the same ID in every organisation.
LEXWARE_INCOME_CATEGORY = "8f8664a1-fd86-11e1-a21f-0800200c9a66"


class InvoiceFormat(models.TextChoices):
    """The format of an outgoing invoice (DOK-049)."""

    XRECHNUNG = "xrechnung", _("XRechnung – PDF and XML apart")
    ZUGFERD = "zugferd", _("ZUGFeRD / Factur-X – one PDF with the invoice inside")


class AccountingSettings(SingletonModel):
    """How invoices reach the accounting: Lexware Office (DOK-011) and the DATEV export (DOK-012).

    The API key of Lexware Office is stored encrypted (``core.crypto``) and
    never shown again; only its last four characters are kept as a hint.
    Mappings per tax rate are keyed by :func:`rate_key`; an empty mapping
    means the default: the category "Einnahmen" in Lexware Office, the
    revenue account of :data:`DEFAULT_REVENUE_ACCOUNTS` in DATEV.
    """

    # --- Lexware Office (DOK-011) ---
    lexware_enabled = models.BooleanField(_("hand invoices to Lexware Office"), default=False)
    lexware_api_key_encrypted = models.TextField(blank=True, editable=False)
    lexware_api_key_hint = models.CharField(max_length=8, blank=True, editable=False)
    lexware_automatic = models.BooleanField(
        _("hand over at once"),
        default=False,
        help_text=_("Every invoice and cancellation goes to Lexware Office as soon as it is made."),
    )
    lexware_collective_contact = models.BooleanField(
        _("book on the collective contact"),
        default=False,
        help_text=_("Instead of finding or creating the customer in Lexware Office."),
    )
    #: Posting category per tax rate, e.g. {"0": "<uuid>"}; missing rates take "Einnahmen".
    lexware_categories = models.JSONField(_("posting categories"), default=dict, blank=True)
    #: The income categories Lexware Office named at the last check: [{"id": …, "name": …}].
    lexware_category_choices = models.JSONField(default=list, blank=True, editable=False)
    lexware_organization = models.CharField(max_length=200, blank=True, editable=False)
    lexware_checked_at = models.DateTimeField(null=True, blank=True, editable=False)

    # --- DATEV (DOK-012) ---
    datev_consultant_number = models.PositiveIntegerField(
        _("consultant number"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1001), MaxValueValidator(9999999)],
        help_text=_("The tax adviser's number at DATEV (Beraternummer)."),
    )
    datev_client_number = models.PositiveIntegerField(
        _("client number"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99999)],
        help_text=_("The company's number at the tax adviser (Mandantennummer)."),
    )
    datev_fiscal_year_start = models.PositiveSmallIntegerField(
        _("fiscal year begins in"),
        default=1,
        choices=[(month, month) for month in range(1, 13)],
        help_text=_("The month; January when the fiscal year is the calendar year."),
    )
    datev_account_length = models.PositiveSmallIntegerField(
        _("length of general ledger accounts"),
        default=4,
        validators=[MinValueValidator(4), MaxValueValidator(8)],
        help_text=_(
            "Number of digits of the general ledger accounts: 4 in most companies. Debtor accounts have one digit more."
        ),
    )
    datev_chart = models.CharField(
        _("chart of accounts"), max_length=5, choices=ChartOfAccounts.choices, default=ChartOfAccounts.SKR03
    )
    #: Revenue account per tax rate, e.g. {"19": "8401"}; missing rates take the default of the chart.
    datev_revenue_accounts = models.JSONField(_("revenue accounts"), default=dict, blank=True)
    datev_debitor_mode = models.CharField(
        _("debtor accounts"), max_length=12, choices=DebitorMode.choices, default=DebitorMode.PER_CUSTOMER
    )
    datev_debitor_offset = models.PositiveIntegerField(
        _("added to the customer number"),
        default=0,
        help_text=_("Customer 10001 with 0 becomes debtor 10001, with 10000 debtor 20001."),
    )
    datev_collective_account = models.PositiveIntegerField(
        _("collective debtor account"), null=True, blank=True, help_text=_("e.g. 10000")
    )

    # --- The e-invoice (DOK-042, DOK-049), the archive (DOK-043) and the EÜR (DOK-045) ---
    invoice_format = models.CharField(
        _("format of the invoice"),
        max_length=10,
        choices=InvoiceFormat.choices,
        default=InvoiceFormat.XRECHNUNG,
        help_text=_(
            "XRechnung: the PDF and, apart, the XML. ZUGFeRD / Factur-X: one PDF/A-3 with the invoice data inside. "
            "Valid for invoices made from now on."
        ),
    )
    einvoice_blocks = models.BooleanField(
        _("do not issue an invoice with errors"),
        default=False,
        help_text=_(
            "Off: errors of the check against the rules of the e-invoice are shown and the invoice is issued all the same."
        ),
    )
    small_business = models.BooleanField(
        _("small business (§ 19 UStG)"),
        default=False,
        help_text=_("The EÜR then counts gross, without turnover tax and input tax."),
    )
    retention_invoice_years = models.PositiveSmallIntegerField(
        _("retention of invoices and vouchers (years)"),
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text=_("Eight years for accounting vouchers (§ 147 AO); the period ends with the calendar year."),
    )
    retention_letter_years = models.PositiveSmallIntegerField(
        _("retention of business letters (years)"),
        default=6,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text=_("Six years for offers, order confirmations and delivery notes."),
    )
    archive_check_days = models.PositiveSmallIntegerField(
        _("every file checked within (days)"),
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text=_("The nightly job checks a part of the archive so that every file is checked in this time."),
    )

    audit_exclude = frozenset(
        {
            "lexware_api_key_encrypted",
            "lexware_api_key_hint",
            "lexware_category_choices",
            "lexware_organization",
            "lexware_checked_at",
        }
    )

    class Meta:
        verbose_name = _("accounting settings")
        verbose_name_plural = _("accounting settings")

    def __str__(self) -> str:
        return str(_("Accounting"))

    # The key is written and read only through these; forms and the API never show it (DOK-011).
    def set_lexware_api_key(self, key: str) -> None:
        """Store the API key of Lexware Office encrypted; an empty key removes it."""
        from rentalars.core.crypto import encrypt_secret

        key = "".join(key.split())
        self.lexware_api_key_encrypted = encrypt_secret(key)
        self.lexware_api_key_hint = f"…{key[-4:]}" if len(key) > 8 else ("…" if key else "")

    @property
    def lexware_api_key(self) -> str:
        """The API key in clear text, for the requests.

        Raises:
            SecretUnreadableError: ``secret_key`` changed since the key was stored.
        """
        from rentalars.core.crypto import decrypt_secret

        return decrypt_secret(self.lexware_api_key_encrypted)

    @property
    def has_lexware_api_key(self) -> bool:
        """Whether an API key is stored."""
        return bool(self.lexware_api_key_encrypted)

    def lexware_category_for(self, percent: Any) -> str:
        """The posting category of a tax rate (DOK-011)."""
        return (self.lexware_categories or {}).get(rate_key(percent)) or LEXWARE_INCOME_CATEGORY

    def default_revenue_account(self, percent: Any) -> str:
        """The revenue account the chart of accounts has for a tax rate; "" if it has none (DOK-012).

        With longer general ledger accounts DATEV fills the standard accounts up with zeros: 8400 becomes 84000.
        """
        account = DEFAULT_REVENUE_ACCOUNTS.get(self.datev_chart, {}).get(rate_key(percent), "")
        return account.ljust(self.datev_account_length, "0") if account else ""

    def revenue_account_for(self, percent: Any) -> str:
        """The revenue account of a tax rate: the one entered, else the default of the chart (DOK-012)."""
        return (self.datev_revenue_accounts or {}).get(rate_key(percent)) or self.default_revenue_account(percent)

    @property
    def debitor_range(self) -> tuple[int, int]:
        """The numbers DATEV takes as debitors: 10000 to 69999 with general ledger accounts of four digits."""
        base = 10**self.datev_account_length
        return base, 7 * base - 1

    def clean(self) -> None:
        """The rules of DOK-011 and DOK-012 for the settings, shared by the page and the API."""
        import re

        super().clean()
        errors: dict[str, list[str]] = {}
        if self.lexware_enabled and not self.lexware_api_key_encrypted:
            errors.setdefault("lexware_enabled", []).append(_("Enter the API key of Lexware Office first."))
        uuid = re.compile(r"^[0-9a-fA-F-]{32,40}$")
        rate = re.compile(r"^\d{1,3}(\.\d{1,2})?$")
        for key, value in (self.lexware_categories or {}).items():
            if not rate.match(str(key)) or not uuid.match(str(value)):
                errors.setdefault("lexware_categories", []).append(
                    _("“%(value)s” for %(rate)s %% is not the ID of a posting category of Lexware Office.")
                    % {"value": value, "rate": key}
                )
        for key, account in (self.datev_revenue_accounts or {}).items():
            if not rate.match(str(key)) or not str(account).isdigit() or len(str(account)) != self.datev_account_length:
                errors.setdefault("datev_revenue_accounts", []).append(
                    _("The revenue account for %(rate)s %% must have exactly %(digits)d digits.")
                    % {"rate": key, "digits": self.datev_account_length}
                )
        if self.datev_debitor_mode == DebitorMode.COLLECTIVE:
            low, high = self.debitor_range
            if self.datev_collective_account is None or not low <= self.datev_collective_account <= high:
                errors.setdefault("datev_collective_account", []).append(
                    _("A debtor account lies between %(low)d and %(high)d.") % {"low": low, "high": high}
                )
        if errors:
            raise ValidationError(errors)


class TransferState(models.TextChoices):
    """Where the handing over of a document to Lexware Office stands (DOK-011)."""

    QUEUED = "queued", _("waiting")
    RUNNING = "running", _("running")
    DONE = "done", _("handed over")
    FAILED = "failed", _("failed")


class LexwareTransfer(models.Model):
    """The handing over of one invoice or cancellation to Lexware Office (DOK-011).

    One per document: what was handed over is noted here, and nothing is
    handed over twice. The voucher ID is stored as soon as Lexware Office
    names it, so that a later attempt only adds what is missing.
    """

    document = models.OneToOneField(
        Document, verbose_name=_("document"), on_delete=models.PROTECT, related_name="lexware_transfer"
    )
    state = models.CharField(_("state"), max_length=10, choices=TransferState.choices, default=TransferState.QUEUED)
    voucher_id = models.CharField(_("voucher in Lexware Office"), max_length=40, blank=True)
    contact_id = models.CharField(_("contact in Lexware Office"), max_length=40, blank=True)
    pdf_uploaded = models.BooleanField(_("PDF handed over"), default=False)
    transferred_at = models.DateTimeField(_("handed over"), null=True, blank=True)
    error = models.TextField(_("error"), blank=True)
    #: What kind of error: "contact_conflict", "auth", "rate_limit", "rejected", "unreachable", "server", "other".
    error_code = models.CharField(max_length=20, blank=True)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    requested_at = models.DateTimeField(_("requested"), default=timezone.now)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(default=timezone.now)
    job = models.ForeignKey(
        "core.BackgroundJob", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        verbose_name = _("handing over to Lexware Office")
        verbose_name_plural = _("handing over to Lexware Office")
        ordering = ["-requested_at", "-id"]

    def __str__(self) -> str:
        return f"{self.document.number}: {self.get_state_display()}"

    @property
    def is_done(self) -> bool:
        """Whether the document is in Lexware Office with its PDF."""
        return self.state == TransferState.DONE

    @property
    def is_pending(self) -> bool:
        """Whether the handing over waits or runs."""
        return self.state in {TransferState.QUEUED, TransferState.RUNNING}


# --- Payments, check of the e-invoice, archive -----------------------------------------------------------------


class OutgoingPayment(PaymentBase):
    """A payment of a customer on an invoice (DOK-048); voided, not changed or deleted."""

    document = models.ForeignKey(Document, verbose_name=_("invoice"), on_delete=models.PROTECT, related_name="payments")

    audit_sensitive = {"amount": SpecialRight.PRICES}

    class Meta(PaymentBase.Meta):
        verbose_name = _("payment received")
        verbose_name_plural = _("payments received")
        indexes = [models.Index(fields=["paid_on"], name="outpay_paid_on_idx")]

    def __str__(self) -> str:
        return f"{self.document.number}: {self.amount}"

    def audit_parent(self) -> models.Model | None:
        """Show the payment in the history of the project or the customer of the invoice."""
        return self.document.project or self.document.customer


class DocumentCheck(models.Model):
    """The result of the check of the e-invoice of a document against the rules (DOK-042).

    The document is never changed; its check is kept beside it and made again on request.
    """

    document = models.OneToOneField(
        Document, verbose_name=_("document"), on_delete=models.CASCADE, related_name="einvoice_check"
    )
    checked_at = models.DateTimeField(_("checked"), default=timezone.now)
    syntax = models.CharField(max_length=8, blank=True)
    profile = models.CharField(max_length=40, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    #: [{"rule": "BR-DE-15", "severity": "error", "message": "…", "location": "…"}]
    findings = models.JSONField(default=list, blank=True)
    ruleset = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = _("check of the e-invoice")
        verbose_name_plural = _("checks of the e-invoices")

    def __str__(self) -> str:
        return f"{self.document.number}: {self.error_count} / {self.warning_count}"

    @property
    def ok(self) -> bool:
        """Whether no rule was broken."""
        return self.error_count == 0


class BankImport(models.Model):
    """One bank statement file that was read in (DOK-050): CAMT.053 or a CSV file of the bank.

    The file itself is not kept; the transactions it held are (:class:`BankTransaction`). The checksum stops the same file
    from being read twice.
    """

    name = models.CharField(_("file"), max_length=200)
    sha256 = models.CharField(max_length=64, unique=True)
    file_format = models.CharField(_("format"), max_length=10)
    account_iban = models.CharField(_("account"), max_length=42, blank=True)
    first_day = models.DateField(_("first day"), null=True, blank=True)
    last_day = models.DateField(_("last day"), null=True, blank=True)
    imported_at = models.DateTimeField(_("read in"), default=timezone.now)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    new_count = models.PositiveIntegerField(_("new transactions"), default=0)
    skipped_count = models.PositiveIntegerField(_("already known"), default=0)

    class Meta:
        verbose_name = _("bank statement")
        verbose_name_plural = _("bank statements")
        ordering = ["-imported_at", "-id"]

    def __str__(self) -> str:
        return self.name


class BankTransaction(models.Model):
    """A booking of the bank account, read from a statement; matched to a payment on request, never automatically."""

    bank_import = models.ForeignKey(
        BankImport, verbose_name=_("bank statement"), on_delete=models.PROTECT, related_name="transactions"
    )
    booked_on = models.DateField(_("booked on"), db_index=True)
    #: Positive: money came in; negative: money left the account.
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    counterparty = models.CharField(_("counterparty"), max_length=200, blank=True)
    counterparty_iban = models.CharField(_("IBAN of the counterparty"), max_length=42, blank=True)
    purpose = models.CharField(_("purpose"), max_length=500, blank=True)
    end_to_end_id = models.CharField(_("end-to-end ID"), max_length=140, blank=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    ignored_at = models.DateTimeField(_("ignored"), null=True, blank=True)
    ignored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ignore_reason = models.CharField(_("reason"), max_length=250, blank=True)
    outgoing_payment = models.ForeignKey(
        "documents.OutgoingPayment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bank_transactions",
        verbose_name=_("payment received"),
    )
    incoming_payment = models.ForeignKey(
        "incoming.IncomingPayment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bank_transactions",
        verbose_name=_("payment made"),
    )
    matched_at = models.DateTimeField(_("matched"), null=True, blank=True)
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("bank transaction")
        verbose_name_plural = _("bank transactions")
        ordering = ["-booked_on", "-id"]
        indexes = [models.Index(fields=["booked_on", "id"], name="banktx_day_idx")]

    def __str__(self) -> str:
        return f"{self.booked_on} {self.amount} {self.counterparty}".strip()

    @property
    def payment(self) -> Any:
        """The payment this booking was matched to, if any (voided or not)."""
        return self.outgoing_payment or self.incoming_payment

    @property
    def state(self) -> str:
        """``booked`` (matched to a payment that counts), ``ignored`` or ``open`` (also when the payment was voided)."""
        if self.ignored_at is not None:
            return "ignored"
        payment = self.payment
        if payment is not None and payment.voided_at is None:
            return "booked"
        return "open"


class ArchiveSource(models.TextChoices):
    """What an archive entry keeps."""

    DOCUMENT = "document", _("outgoing document")
    INCOMING = "incoming", _("incoming invoice")


class ArchiveStatus(models.TextChoices):
    """What the last check found."""

    OK = "ok", _("unchanged")
    CHANGED = "changed", _("changed")
    MISSING = "missing", _("missing")
    DELETED = "deleted", _("deleted after the retention period")


class ArchiveRecord(models.Model):
    """One voucher in the archive: files with their checksums and the retention period (DOK-043).

    The entry stays when the voucher is deleted after its retention period (``status`` "deleted"), so that the
    protocol of the archive is complete. It points to the voucher by kind and ID, not by a foreign key.
    """

    source = models.CharField(_("kind"), max_length=10, choices=ArchiveSource.choices)
    source_id = models.PositiveBigIntegerField(_("ID of the voucher"))
    reference = models.CharField(_("number"), max_length=80, blank=True)
    title = models.CharField(_("title"), max_length=160, blank=True)
    voucher_date = models.DateField(_("voucher date"), null=True, blank=True)
    #: [{"role": "pdf", "name": "documents/…", "sha256": "…", "size": 1234}]
    files = models.JSONField(_("files"), default=list)
    registered_at = models.DateTimeField(_("archived"), default=timezone.now)
    retain_until = models.DateField(_("retain until"))
    status = models.CharField(_("status"), max_length=10, choices=ArchiveStatus.choices, default=ArchiveStatus.OK)
    last_checked_at = models.DateTimeField(_("last checked"), null=True, blank=True)
    finding = models.CharField(_("finding"), max_length=250, blank=True)

    class Meta:
        verbose_name = _("archive entry")
        verbose_name_plural = _("archive entries")
        ordering = ["-registered_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["source", "source_id"], name="archive_source_unique")]
        indexes = [models.Index(fields=["last_checked_at"], name="archive_checked_idx")]

    def __str__(self) -> str:
        return f"{self.reference} ({self.get_status_display()})"

    @property
    def is_retained(self) -> bool:
        """Whether the retention period is still running."""
        return self.retain_until >= timezone.localdate()
