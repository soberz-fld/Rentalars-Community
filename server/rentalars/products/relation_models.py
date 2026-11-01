# SPDX-License-Identifier: GPL-3.0-or-later
"""Accessories and replacement products (accessory and replacement suggestions; PRD-023, VFG-015).

"Ersatz- und Zubehörvorschläge": a product can name

* **accessories** (Zubehör) – other products that belong with it: the cable for the speaker, the stand for the
  light. Each is *recommended* or *required*, with the number of pieces it takes per piece of the product, and
* **replacements** (Ersatz) – products that can stand in when the product is short in a period, with the number
  of pieces per missing piece.

The relations are kept at the level of products, because that is what projects are planned with (PRD-001): one
product, whichever material models stand behind it. The pages of a product and of its material models show and
change them; the planning of a project reads them to make suggestions (``products.suggestions``). A planner who
does not want a suggestion in one project dismisses it there (``DismissedSuggestion``). Imported at the end of
``rentalars/products/models.py`` so that Django finds the tables.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel
from rentalars.products.models import ProductKind


class RelationKind(models.TextChoices):
    """What a related product is to a product."""

    ACCESSORY = "accessory", _("accessory")
    REPLACEMENT = "replacement", _("replacement")


#: The kinds of product that can be suggested and planned as material: rented or sold from stock, or a kit.
SUGGESTIBLE_KINDS = frozenset({ProductKind.RENTAL.value, ProductKind.SALE.value, ProductKind.KIT.value})


class ProductRelation(AuditedModel):
    """A product that is an accessory or a replacement of another product (PRD-023, VFG-015).

    Attributes:
        product: The product that has the accessory or replacement.
        related_product: The accessory or replacement.
        kind: :class:`RelationKind`.
        position: Where it stands in the list of the product (the suggestions follow this order).
        note: A remark for the planner, e.g. "for the 3-pin plug".
        is_required: Accessories only: the product cannot be used without it – the suggestion says so.
        quantity_per_piece: Pieces of ``related_product`` per piece of ``product`` – for an accessory how many go
            with one piece, for a replacement how many replace one missing piece.
    """

    product = models.ForeignKey(
        "products.Product", verbose_name=_("product"), on_delete=models.CASCADE, related_name="relations"
    )
    related_product = models.ForeignKey(
        "products.Product",
        verbose_name=_("related product"),
        on_delete=models.CASCADE,
        related_name="related_from",
    )
    kind = models.CharField(_("kind"), max_length=12, choices=RelationKind.choices, default=RelationKind.ACCESSORY)
    position = models.PositiveSmallIntegerField(_("position"), default=0)
    note = models.CharField(_("note"), max_length=250, blank=True)
    is_required = models.BooleanField(
        _("required"),
        default=False,
        help_text=_("Accessories only: the product cannot be used without it. Otherwise it is recommended."),
    )
    quantity_per_piece = models.DecimalField(
        _("pieces per piece"),
        max_digits=7,
        decimal_places=2,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("How many pieces of the related product go with one piece of this product."),
    )

    class Meta:
        verbose_name = _("accessory or replacement")
        verbose_name_plural = _("accessories and replacements")
        ordering = ["kind", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "related_product", "kind"], name="product_relation_unique")
        ]

    def __str__(self) -> str:
        return f"{self.product.article_number} → {self.related_product.article_number} ({self.kind})"

    def audit_parent(self) -> models.Model | None:
        """Show changes in the history of the product."""
        return self.product

    def clean(self) -> None:
        """A product is no accessory or replacement of itself; both can be suggested; customer material stays with its owner."""
        super().clean()
        if self.product_id is None or self.related_product_id is None:
            return
        if self.product_id == self.related_product_id:
            raise ValidationError({"related_product": _("A product cannot be its own accessory or replacement.")})
        for product, field in ((self.product, "product"), (self.related_product, "related_product")):
            if product.kind not in SUGGESTIBLE_KINDS:
                raise ValidationError(
                    {
                        field: _(
                            "%(product)s cannot have accessories or replacements: only rented and sold products "
                            "and kits can."
                        )
                        % {"product": product.article_number}
                    }
                )
        if self.related_product.owner_id != self.product.owner_id:
            raise ValidationError(
                {"related_product": _("Customer material goes only with material of the same customer.")}
            )
        if self.kind == RelationKind.REPLACEMENT:
            self.is_required = False  # a replacement is never "required"


class DismissedSuggestion(models.Model):
    """A suggestion a planner dismissed in one project; it is not made again there.

    The suggestion is the relation (``ProductRelation``); the project, who and when are kept so that the
    project's planners can see and undo it.
    """

    project = models.ForeignKey(
        "projects.Project", verbose_name=_("project"), on_delete=models.CASCADE, related_name="dismissed_suggestions"
    )
    relation = models.ForeignKey(
        ProductRelation, verbose_name=_("accessory or replacement"), on_delete=models.CASCADE, related_name="dismissals"
    )
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    dismissed_at = models.DateTimeField(_("dismissed"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("dismissed suggestion")
        verbose_name_plural = _("dismissed suggestions")
        constraints = [models.UniqueConstraint(fields=["project", "relation"], name="dismissed_suggestion_unique")]

    def __str__(self) -> str:
        return f"{self.project_id}: {self.relation}"
