# SPDX-License-Identifier: GPL-3.0-or-later
"""The record of a used sale from stock ("Gebrauchtverkauf aus Bestand"; MAT-087).

Requirement: used sales from stock as well. An item (or a quantity of bulk material) is sold out of the stock. The
item leaves the stock with the status "sold" (the existing mechanics of ``MaterialItem.status``); this table keeps
what the sale was: buyer, day, price, the book value at the sale and the gain or loss against it. A sale is
reversed (Storno), never deleted: the record stays with who reversed it and when.

Imported at the end of ``rentalars/material/models.py`` so that Django finds the table.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel

#: How the book value of a sale came about.
BASIS_CALCULATED = "calculated"  # worked out from the asset data of the item (cost, kind, useful life, date)
BASIS_UNKNOWN = "unknown"  # the item is not an asset in the books (or lacks cost or date): the book value was set to 0


class SaleFromStock(AuditedModel):
    """One used sale out of the stock: the item, the buyer, the price and the result against the book value.

    For bulk material ``quantity`` pieces of the row are sold and the cost fields of the row are reduced by their
    share (``price_part``, ``ancillary_part`` keep the amounts, so that a reversal puts them back exactly).
    """

    item = models.ForeignKey(
        "material.MaterialItem", verbose_name=_("item"), on_delete=models.PROTECT, related_name="stock_sales"
    )
    quantity = models.PositiveIntegerField(
        _("quantity"), default=1, validators=[MinValueValidator(1)], help_text=_("Pieces sold; 1 for an item.")
    )
    sold_on = models.DateField(_("sold on"))
    customer = models.ForeignKey(
        "customers.Customer",
        verbose_name=_("customer"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    contact = models.ForeignKey(
        "customers.Contact",
        verbose_name=_("contact"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    buyer_name = models.CharField(
        _("buyer"), max_length=200, help_text=_("A customer or contact, or a name typed in. Kept as written.")
    )
    net_price = models.DecimalField(
        _("price (net)"), max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    tax_rate = models.ForeignKey(
        "masterdata.TaxRate",
        verbose_name=_("tax rate"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    tax_percent = models.DecimalField(_("tax rate in percent"), max_digits=5, decimal_places=2, default=Decimal("0"))
    note = models.TextField(_("note"), blank=True)

    # What the item was in the books when it was sold – kept, because the item's data may change afterwards.
    asset_kind = models.CharField(_("kind of asset"), max_length=12, blank=True)
    cost = models.DecimalField(
        _("acquisition cost of the pieces sold (net)"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    accumulated_depreciation = models.DecimalField(
        _("depreciation until the sale"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    book_value = models.DecimalField(_("book value at the sale"), max_digits=12, decimal_places=2, default=Decimal("0"))
    book_value_basis = models.CharField(_("book value"), max_length=12, default=BASIS_CALCULATED)
    gain_loss = models.DecimalField(
        _("gain or loss"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text=_("Price minus book value; a negative amount is a loss."),
    )

    # How to put the item back when the sale is reversed.
    previous_status = models.CharField(_("status before the sale"), max_length=12)
    previous_reason = models.CharField(_("reason before the sale"), max_length=250, blank=True)
    row_quantity_before = models.PositiveIntegerField(_("quantity of the row before the sale"), default=1)
    item_left = models.BooleanField(
        _("the item left the stock"),
        default=True,
        help_text=_("Yes: the item is sold. No: a part of a bulk row was sold, the row stays."),
    )
    price_part = models.DecimalField(
        _("purchase price of the pieces sold"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    ancillary_part = models.DecimalField(
        _("ancillary cost of the pieces sold"), max_digits=12, decimal_places=2, null=True, blank=True
    )

    #: The draft of the invoice made for this sale ("Rechnung dazu erstellen") while it is a draft ...
    invoice_draft_id = models.PositiveBigIntegerField(_("draft of the invoice"), null=True, blank=True, editable=False)
    #: ... and the invoice once it was issued: a sale has one invoice, and one with an invoice is not reversed alone.
    document = models.ForeignKey(
        "documents.Document",
        verbose_name=_("invoice"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_sales",
        editable=False,
    )

    sold_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    cancelled_at = models.DateTimeField(_("reversed"), null=True, blank=True, editable=False)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    cancel_reason = models.CharField(_("reason for the reversal"), max_length=250, blank=True)

    audit_sensitive = {
        "net_price": SpecialRight.PURCHASE_PRICES,
        "tax_percent": SpecialRight.PURCHASE_PRICES,
        "cost": SpecialRight.PURCHASE_PRICES,
        "accumulated_depreciation": SpecialRight.PURCHASE_PRICES,
        "book_value": SpecialRight.PURCHASE_PRICES,
        "gain_loss": SpecialRight.PURCHASE_PRICES,
        "price_part": SpecialRight.PURCHASE_PRICES,
        "ancillary_part": SpecialRight.PURCHASE_PRICES,
    }

    class Meta:
        verbose_name = _("sale from stock")
        verbose_name_plural = _("sales from stock")
        ordering = ["-sold_on", "-id"]
        indexes = [models.Index(fields=["sold_on"], name="stocksale_sold_on_idx")]

    def __str__(self) -> str:
        return f"{self.item.display_id} → {self.buyer_name}"

    def audit_parent(self) -> models.Model | None:
        """Show changes in the history of the item."""
        return self.item

    @property
    def kind_label(self) -> str:
        """The kind of asset in words; empty when the item was no asset."""
        from rentalars.material.models import AssetKind

        return str(AssetKind(self.asset_kind).label) if self.asset_kind in AssetKind.values else ""

    @property
    def is_cancelled(self) -> bool:
        """Whether the sale was reversed."""
        return self.cancelled_at is not None

    @property
    def tax_amount(self) -> Decimal:
        """The tax on the price, rounded to cents."""
        from rentalars.core.money import percentage_of

        return percentage_of(self.net_price, self.tax_percent)

    @property
    def gross_price(self) -> Decimal:
        """The price with tax."""
        return self.net_price + self.tax_amount
