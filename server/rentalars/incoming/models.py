# SPDX-License-Identifier: GPL-3.0-or-later
"""Incoming invoices and their positions (DOK-023, DOK-024).

``IncomingInvoice``
    One invoice a supplier sent: the file as it came, the head (supplier, number, date, due date, currency, amounts),
    a note, the status and what the reading found. The user corrects everything the reading proposed.

``InvoicePosition``
    One position: goods that become items or bulk quantities, ancillary cost (freight, packaging, customs …) that
    is spread over the goods, or something else (a service, a deposit) that is only kept. Which items a position
    produced is written at the items (``MaterialItem.source_position``) – that is the traceability and the
    protection against booking a position twice.

Each position names its tax account (Steuerkonto, master data ``TaxAccount``): in the pages a position is
a *Kontierung* – one row of how the document is split over the accounts – with description, account, kind and net
amount; quantity, article number and manufacturer are kept (the reading fills them, "Book in goods" uses them) but
are not part of the form of the document any more.

Imported by the app registry as ``rentalars.incoming.models``; the tables are named ``incoming_*``.
"""

from __future__ import annotations

import secrets
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.money import money
from rentalars.core.payment_base import PaymentBase
from rentalars.masterdata.models import StorageLocation, Supplier, TaxAccount
from rentalars.material.models import AssetKind, MaterialModel

#: The most positions of one invoice – as for "Kauf einpflegen" (``purchases.MAX_POSITIONS``).
MAX_POSITIONS = 100


class InvoiceStatus(models.TextChoices):
    """Where an incoming invoice stands: to be looked at, looked at, or its goods are in the stock."""

    OPEN = "open", _("open")
    CHECKED = "checked", _("checked")
    BOOKED_IN = "booked_in", _("booked in")


class PositionType(models.TextChoices):
    """What a position is: goods for the stock, ancillary cost to spread over the goods, or something else."""

    GOODS = "goods", _("material")
    ANCILLARY = "ancillary", _("ancillary cost")
    OTHER = "other", _("other")


class AllocationKey(models.TextChoices):
    """By what the ancillary costs of an invoice are spread over its goods: value, quantity or weight."""

    VALUE = "value", _("by value")
    QUANTITY = "quantity", _("by quantity")
    WEIGHT = "weight", _("by weight")


class ReadingState(models.TextChoices):
    """What became of reading the file of an invoice."""

    NONE = "none", _("not read")
    RUNNING = "running", _("being read")
    DONE = "done", _("read")
    FAILED = "failed", _("not readable")


def invoice_file_path(instance: IncomingInvoice, filename: str) -> str:
    """Store the files of incoming invoices in a folder of their own under a random name (see ``material_file_path``)."""
    extension = Path(filename).suffix.lower()[:10]
    return f"incoming/{timezone.localdate():%Y}/{secrets.token_hex(12)}{extension}"


class IncomingInvoice(AuditedModel):
    """An invoice a supplier sent, with its file, its head, a note and a status."""

    supplier = models.ForeignKey(
        Supplier,
        verbose_name=_("supplier"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incoming_invoices",
    )
    #: The supplier as the invoice (or the user) names it: kept when the supplier is not in the master data yet.
    supplier_name = models.CharField(_("supplier as named on the invoice"), max_length=120, blank=True)
    invoice_number = models.CharField(_("invoice number"), max_length=60, blank=True)
    invoice_date = models.DateField(_("invoice date"), null=True, blank=True)
    due_date = models.DateField(_("due date"), null=True, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    #: Empty until it is entered – an invoice in another currency is not booked in 1:1 by accident.
    exchange_rate = models.DecimalField(
        _("exchange rate"),
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        default=None,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_(
            "Euros for one unit of the currency. Needed for an invoice in another currency than the euro: "
            "booking in waits for it."
        ),
    )
    total_net = models.DecimalField(_("total net"), max_digits=12, decimal_places=2, null=True, blank=True)
    total_tax = models.DecimalField(_("tax"), max_digits=12, decimal_places=2, null=True, blank=True)
    total_gross = models.DecimalField(_("total gross"), max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.OPEN)
    allocation_key = models.CharField(
        _("ancillary costs are spread"),
        max_length=10,
        choices=AllocationKey.choices,
        default=AllocationKey.VALUE,
        help_text=_("By what the ancillary costs of this invoice are spread over its goods."),
    )
    note = models.TextField(_("note"), blank=True)
    file = models.FileField(_("file"), upload_to=invoice_file_path, max_length=200)
    original_name = models.CharField(_("file name"), max_length=255)
    #: The XML of an e-invoice that came attached to a PDF (ZUGFeRD / Factur-X); an uploaded XML is ``file``.
    xml_file = models.FileField(
        _("e-invoice XML"), upload_to=invoice_file_path, max_length=200, blank=True, editable=False
    )
    #: "ubl" or "cii" when the file is a structured e-invoice that could be read, else empty.
    einvoice_format = models.CharField(max_length=8, blank=True, editable=False)
    size = models.PositiveBigIntegerField(_("size"), default=0)
    #: SHA-256 of the file: the same file twice is noticed (``services.duplicates``).
    content_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    reading_state = models.CharField(
        max_length=10, choices=ReadingState.choices, default=ReadingState.NONE, editable=False
    )
    reading_job = models.ForeignKey(
        "core.BackgroundJob", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    #: What the reading says about itself: ``source`` ("ai", "text", ""), ``ai`` (model, provider, local),
    #: ``error``, ``note`` (e.g. only the first pages were read), ``at`` (when), ``hints``.
    reading = models.JSONField(default=dict, blank=True, editable=False)
    #: DOK-042: the check of the e-invoice against the rules – {} while there was none; see ``einvoice_rules``.
    einvoice_check = models.JSONField(default=dict, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    created_at = models.DateTimeField(_("uploaded"), default=timezone.now, editable=False)

    audit_exclude = frozenset(
        {
            "file",
            "xml_file",
            "einvoice_format",
            "einvoice_check",
            "size",
            "content_hash",
            "reading",
            "reading_job",
            "reading_state",
        }
    )
    audit_sensitive = {
        "total_net": SpecialRight.PURCHASE_PRICES,
        "total_tax": SpecialRight.PURCHASE_PRICES,
        "total_gross": SpecialRight.PURCHASE_PRICES,
    }

    class Meta:
        verbose_name = _("incoming invoice")
        verbose_name_plural = _("incoming invoices")
        ordering = ["-invoice_date", "-pk"]
        indexes = [models.Index(fields=["status"], name="incoming_status_idx")]

    def __str__(self) -> str:
        return " ".join(part for part in (self.supplier_label, self.invoice_number) if part) or self.original_name

    @property
    def supplier_label(self) -> str:
        """The supplier of the master data, else the name on the invoice."""
        return self.supplier.name if self.supplier_id else self.supplier_name

    @property
    def is_pdf(self) -> bool:
        """Whether the file is a PDF (only those are read)."""
        return self.original_name.lower().endswith(".pdf")

    @property
    def is_xml(self) -> bool:
        """Whether the file itself is an XML (an uploaded e-invoice)."""
        return self.original_name.lower().endswith(".xml")

    @property
    def xml_name(self) -> str:
        """The stored name of the e-invoice XML – the file itself or the one taken out of the PDF; empty if there is none."""
        if self.xml_file:
            return self.xml_file.name
        return self.file.name if self.is_xml and self.file else ""

    @property
    def is_einvoice(self) -> bool:
        """Whether the invoice is a structured e-invoice (XML, or a PDF with a readable XML attached)."""
        return bool(self.einvoice_format)

    @property
    def einvoice(self) -> dict:
        """What reading the e-invoice found out about the file (profile, type, IBAN, warnings …); empty otherwise."""
        return (self.reading or {}).get("einvoice") or {}

    @property
    def is_picture(self) -> bool:
        """Whether the file is a picture the browser shows."""
        return self.original_name.lower().rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "gif", "webp"}

    @property
    def rate(self) -> Decimal | None:
        """The factor from the currency of the invoice to euros: 1 for the euro; ``None`` while the rate is not entered."""
        return Decimal("1") if (self.currency or "EUR").upper() == "EUR" else self.exchange_rate

    @property
    def is_foreign_currency(self) -> bool:
        """Whether the invoice is in another currency than the euro."""
        return (self.currency or "EUR").upper() != "EUR"


class InvoicePosition(AuditedModel):
    """One position of an incoming invoice."""

    invoice = models.ForeignKey(IncomingInvoice, on_delete=models.CASCADE, related_name="positions")
    place = models.PositiveSmallIntegerField(_("position"), default=1)
    description = models.CharField(_("description"), max_length=250)
    article_number = models.CharField(_("supplier's article number"), max_length=120, blank=True)
    manufacturer = models.CharField(_("manufacturer"), max_length=120, blank=True)
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=3,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit_price_net = models.DecimalField(
        _("unit price (net)"),
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_("In the currency of the invoice. For ancillary cost: the amount; a discount is negative."),
    )
    tax_rate = models.DecimalField(
        _("tax rate (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    position_type = models.CharField(
        _("kind of position"), max_length=10, choices=PositionType.choices, default=PositionType.GOODS
    )
    asset_kind = models.CharField(
        _("kind of asset"),
        max_length=12,
        choices=AssetKind.choices,
        blank=True,
        help_text=_("Empty: by the limit in the settings – up to it a low-value asset, above it a fixed asset."),
    )
    useful_life_months = models.PositiveSmallIntegerField(
        _("useful life (months)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(600)],
        help_text=_("For a fixed asset. Empty: the standard useful life of the settings."),
    )
    weight_kg = models.DecimalField(
        _("weight of one piece (kg)"),
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Only to spread ancillary costs by weight. Empty: the weight of the model."),
    )
    #: The tax account (Steuerkonto) the net amount of the position is booked to; empty while not chosen.
    tax_account = models.ForeignKey(
        TaxAccount,
        verbose_name=_("tax account"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoice_positions",
        help_text=_(
            "The account of the chart of accounts this amount belongs to. Set up under Master data → Tax accounts."
        ),
    )
    #: A person typed or corrected this position. A new reading of the file never replaces it.
    user_edited = models.BooleanField(default=False, editable=False)
    #: The model this position is booked as (set when it is booked in, or chosen from the proposal).
    material_model = models.ForeignKey(
        MaterialModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="incoming_positions"
    )
    serial_numbers = models.TextField(_("serial numbers"), blank=True)
    storage_location = models.ForeignKey(
        StorageLocation, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    #: What the reading proposed for booking: ``model_id``, ``category_id``, ``product_id``, ``candidates``, ``hints``.
    suggestion = models.JSONField(default=dict, blank=True, editable=False)

    audit_sensitive = {"unit_price_net": SpecialRight.PURCHASE_PRICES}

    class Meta:
        verbose_name = _("invoice position")
        verbose_name_plural = _("invoice positions")
        ordering = ["invoice", "place", "pk"]

    def __str__(self) -> str:
        return f"{self.place}. {self.description}"

    def audit_parent(self) -> models.Model | None:
        """Show changes of a position in the history of its invoice."""
        return self.invoice

    @property
    def line_net(self) -> Decimal | None:
        """Quantity times net unit price in the currency of the invoice, in cents; ``None`` without a price."""
        if self.unit_price_net is None:
            return None
        return money(self.quantity * self.unit_price_net)

    @property
    def is_goods(self) -> bool:
        """Whether the position becomes items or a quantity."""
        return self.position_type == PositionType.GOODS

    @property
    def is_ancillary(self) -> bool:
        """Whether the position is ancillary cost to spread over the goods."""
        return self.position_type == PositionType.ANCILLARY


class IncomingPayment(PaymentBase):
    """A payment to the supplier on an incoming invoice (DOK-048); voided, not changed or deleted."""

    invoice = models.ForeignKey(
        IncomingInvoice, verbose_name=_("invoice"), on_delete=models.PROTECT, related_name="payments"
    )

    audit_sensitive = {"amount": SpecialRight.PURCHASE_PRICES}

    class Meta(PaymentBase.Meta):
        verbose_name = _("payment made")
        verbose_name_plural = _("payments made")
        indexes = [models.Index(fields=["paid_on"], name="inpay_paid_on_idx")]

    def __str__(self) -> str:
        return f"{self.invoice.invoice_number}: {self.amount}"

    def audit_parent(self) -> models.Model | None:
        """Show the payment in the history of the invoice."""
        return self.invoice
