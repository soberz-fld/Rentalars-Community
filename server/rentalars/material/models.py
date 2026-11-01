# SPDX-License-Identifier: GPL-3.0-or-later
"""Material: models and individual items (chapter 5.2).

Two levels (MAT-001):

``MaterialModel``
    An article type of a manufacturer, e.g. "Cordial CPM 5 FM". Holds what
    all its items have in common: name, category, specification.

``MaterialItem``
    One physical piece with its inventory ID, serial number and purchase
    data. For bulk material (cable ties, simple adapters) one row stands for
    a whole quantity instead (MAT-005).

The 13 fields of MAT-011 are split between the two levels as the catalogue
prescribes; the list view, the import and the export show them side by side
in one row per item (MAT-012).
"""

from __future__ import annotations

from decimal import Decimal
from functools import cached_property
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.i18n import local_pattern
from rentalars.core.money import decimal_separator
from rentalars.masterdata.models import Category, Manufacturer, StorageLocation, Supplier
from rentalars.material import partial_dates
from rentalars.material.spots import SPOT_LENGTH, normalise_spot
from rentalars.products.models import Product


class TrackingMode(models.TextChoices):
    """How the stock of a material model is kept (MAT-005)."""

    ITEMS = "items", _("individual items")
    BULK = "bulk", _("bulk quantity")


class AssetKind(models.TextChoices):
    """What an item is in the books: merchandise, a low-value asset (GWG) or a fixed asset (incoming invoices).

    Set when the item is booked in from an incoming invoice (``rentalars.incoming``); the depreciation built on
    top of it reads ``MaterialItem.asset_kind``, ``useful_life_months``, ``acquisition_cost_net`` and ``purchase_date``.
    """

    MERCHANDISE = "merchandise", _("merchandise")
    LOW_VALUE = "low_value", _("low-value asset (GWG)")
    FIXED_ASSET = "fixed_asset", _("fixed asset")


class ItemStatus(models.TextChoices):
    """The life-cycle status of an item (MAT-020, MAT-022)."""

    AVAILABLE = "available", _("available")
    IN_USE = "in_use", _("in use")
    DEFECTIVE = "defective", _("defective")
    IN_REPAIR = "in_repair", _("in repair")
    BLOCKED = "blocked", _("blocked")
    RETIRED = "retired", _("retired")
    SOLD = "sold", _("sold")
    LOST = "lost", _("lost")
    #: Set only by the import of items, when something of a row could not be taken over (the note says what).
    #: Nobody chooses it – it is missing from :data:`SELECTABLE_STATUSES` – and the item is not fit for rental.
    IMPORT_ERROR = "import_error", _("import error")


#: The statuses a person or the API may choose: all but "import error", which only the import sets.
SELECTABLE_STATUSES = tuple(status for status in ItemStatus if status != ItemStatus.IMPORT_ERROR)
SELECTABLE_STATUS_CHOICES = [(status.value, status.label) for status in SELECTABLE_STATUSES]


#: MAT-021: only items in these statuses count towards the plannable stock.
OPERATIONAL_STATUSES = frozenset({ItemStatus.AVAILABLE.value, ItemStatus.IN_USE.value})

#: MAT-022: items in these statuses are archived, never deleted.
ARCHIVED_STATUSES = frozenset({ItemStatus.RETIRED.value, ItemStatus.SOLD.value, ItemStatus.LOST.value})

#: MAT-045: where a defective item can go. Not straight back to "available":
#: somebody has to look at it first – it is repaired, or it leaves the stock.
STATUSES_AFTER_DEFECTIVE = (ItemStatus.IN_REPAIR.value, ItemStatus.RETIRED.value, ItemStatus.SOLD.value)


class ConnectionType(models.TextChoices):
    """How an item sits inside another item (MAT-036)."""

    FIXED = "fixed", _("permanently installed")
    LOOSE = "loose", _("loosely contained")


class ProtectionClass(models.TextChoices):
    """The protection class of an electrical device after DIN EN 61140 (MAT-077).

    Stored and exchanged (import, export, API) as the plain numeral ``I``, ``II`` or ``III``; empty: not an
    electrical device, or not known. The limits of an electrical inspection depend on it (``material.dguv``).
    """

    I = "I", _("I (protective conductor)")  # noqa: E741 – the numeral is the name of the class
    II = "II", _("II (protective insulation)")
    III = "III", _("III (safety extra-low voltage)")


#: From a material model to the fields of its category and of the parent
#: categories they can be inherited from (see ``Category.applicable_fields``).
CATEGORY_FIELD_PATHS = ("category__fields", "category__parent__fields", "category__parent__parent__fields")


class MaterialModelQuerySet(models.QuerySet["MaterialModel"]):
    """Reusable additions for lists of material models."""

    def with_category_fields(self) -> MaterialModelQuerySet:
        """Load the category-specific fields for the whole list at once (MAT-009)."""
        return self.prefetch_related(*CATEGORY_FIELD_PATHS)

    def with_item_count(self) -> MaterialModelQuerySet:
        """Add ``item_count``, the number of items (rows) of each model.

        Counted with a small query per model shown instead of joining all
        items to all models: a list page shows 50 models, the join would
        read every item in the database for them (NFA-012).
        """
        per_model = (
            MaterialItem.objects.filter(material_model=OuterRef("pk"))
            .order_by()
            .values("material_model")
            .annotate(number=Count("pk"))
            .values("number")
        )
        return self.annotate(item_count=Coalesce(Subquery(per_model, output_field=models.IntegerField()), 0))


class MaterialModel(AuditedModel):
    """An article type; the "model" level of MAT-001 and MAT-011.

    ``field_values`` holds the category-specific values (MAT-009, MAT-010) as
    a mapping from the ID of a ``CategoryField`` to the stored text, for
    example ``{"7": "5"}`` for "length: 5 m". The first field of the category
    is "the" category-specific value of MAT-011 no. 5; see
    :attr:`category_specific_value`.
    """

    name = models.CharField(
        _("article name"),
        max_length=200,
        unique=True,
        error_messages={"unique": _("A material model with this article name already exists.")},
    )
    short_name = models.CharField(
        _("short name"), max_length=60, blank=True, help_text=_("For lists and labels. Empty: the article name.")
    )
    category = models.ForeignKey(
        Category, verbose_name=_("category"), on_delete=models.PROTECT, related_name="material_models"
    )
    manufacturer = models.ForeignKey(
        Manufacturer,
        verbose_name=_("manufacturer"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_models",
    )
    # MAT-049: shown as "Beschreibung" everywhere; the field keeps its name ("Spezifikation" of MAT-011).
    specification = models.TextField(_("description"), blank=True, help_text=_("Short technical description."))
    field_values = models.JSONField(_("category-specific values"), default=dict, blank=True)
    default_product = models.ForeignKey(
        Product,
        verbose_name=_("product"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_models",
        help_text=_("Applies to all items of this model unless an item names a different product."),
    )
    tracking_mode = models.CharField(
        _("stock is kept as"), max_length=10, choices=TrackingMode.choices, default=TrackingMode.ITEMS
    )
    # MAT-016: the basis of the weight and volume on packlists (PCK-006).
    weight_kg = models.DecimalField(
        _("weight (kg)"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Of one piece, ready to load (in its case, if it travels in one)."),
    )
    length_cm = models.DecimalField(
        _("length (cm)"), max_digits=7, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    width_cm = models.DecimalField(
        _("width (cm)"), max_digits=7, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    height_cm = models.DecimalField(
        _("height (cm)"), max_digits=7, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    # MAT-049: the power of one piece.
    power_w = models.DecimalField(
        _("power (W)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Electrical power of one piece in watts."),
    )
    # MAT-077: the protection class of its items unless an item has its own (MaterialItem.protection_class_override).
    protection_class = models.CharField(
        _("protection class"),
        max_length=3,
        choices=ProtectionClass.choices,
        blank=True,
        help_text=_(
            "Of an electrical device: I with protective conductor, II with protective insulation, III for safety "
            "extra-low voltage. Empty: not electrical, or not known."
        ),
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    objects = MaterialModelQuerySet.as_manager()

    class Meta:
        verbose_name = _("material model")
        verbose_name_plural = _("material models")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def display_short_name(self) -> str:
        """The short name, falling back to the article name."""
        return self.short_name or self.name

    @property
    def pieces_per_product(self) -> int:
        """How many items of this model make up one piece of its product; 1 without a product.

        The number is set at the product (``Product.pieces_per_product``): it is the product that stands for
        "10 × XLR cable 1.5 m", whichever models and items are behind it.
        """
        return self.default_product.pieces_per_product if self.default_product_id else 1

    @property
    def is_bulk(self) -> bool:
        """Whether this model keeps a quantity instead of individual items."""
        return self.tracking_mode == TrackingMode.BULK

    @property
    def volume_litres(self) -> Decimal | None:
        """The volume of one piece in litres, from its dimensions (MAT-016); ``None`` if one is missing."""
        if self.length_cm is None or self.width_cm is None or self.height_cm is None:
            return None
        return (self.length_cm * self.width_cm * self.height_cm / Decimal(1000)).quantize(Decimal("0.1"))

    @property
    def dimensions_display(self) -> str:
        """The dimensions as ``60 × 40 × 35 cm``; empty if none are given."""
        parts = [self.length_cm, self.width_cm, self.height_cm]
        if all(part is None for part in parts):
            return ""
        return (
            " × ".join(
                "?" if part is None else format(part.normalize(), "f").replace(".", decimal_separator())
                for part in parts
            )
            + " cm"
        )

    def field_display(self, field: Any, overrides: dict[str, str] | None = None) -> str:
        """The value of a category-specific field for people, an item's own value first (MAT-010, MAT-013)."""
        key = str(field.pk)
        if overrides and overrides.get(key):
            return field.display_value(overrides[key])
        return field.display_value(self.field_values.get(key, ""))

    def set_field_value(self, field: Any, raw_value: Any) -> None:
        """Validate and store the value of any category-specific field (MAT-010).

        Raises:
            ValidationError: The value does not fit the type of the field.
        """
        cleaned = field.clean_value(raw_value)
        values = dict(self.field_values or {})
        if cleaned:
            values[str(field.pk)] = cleaned
        else:
            values.pop(str(field.pk), None)
        if field.pk == getattr(self.category.primary_field, "pk", None):
            values.pop("unassigned", None)
        self.field_values = values

    @property
    def category_specific_value(self) -> str:
        """The stored value of the category's first field (MAT-011 no. 5)."""
        field = self.category.primary_field
        unassigned = self.field_values.get("unassigned", "")
        if field is None:
            return unassigned
        return self.field_values.get(str(field.pk), "") or unassigned

    @property
    def category_specific_display(self) -> str:
        """The category-specific value formatted for people, e.g. ``5 m``."""
        field = self.category.primary_field
        unassigned = self.field_values.get("unassigned", "")
        if field is None:
            return unassigned
        return field.display_value(self.field_values.get(str(field.pk), "")) or unassigned

    def set_category_specific_value(self, raw_value: Any) -> None:
        """Validate and store the value of the category's first field.

        If the category has no field defined yet, the text is kept under the
        key ``"unassigned"`` so that nothing typed or imported gets lost.

        Raises:
            ValidationError: The value does not fit the type of the field.
        """
        field = self.category.primary_field
        values = dict(self.field_values or {})
        if field is None:
            text = "" if raw_value is None else str(raw_value).strip()
            if text:
                values["unassigned"] = text
            else:
                values.pop("unassigned", None)
        else:
            cleaned = field.clean_value(raw_value)
            values.pop("unassigned", None)
            if cleaned:
                values[str(field.pk)] = cleaned
            else:
                values.pop(str(field.pk), None)
        self.field_values = values

    def clean(self) -> None:
        """A model can only switch to individual items while its rows allow it."""
        super().clean()
        self.name = (self.name or "").strip()
        if self.pk is not None and self.tracking_mode == TrackingMode.ITEMS:
            if self.items.filter(quantity__gt=1).exists():
                raise ValidationError(
                    {
                        "tracking_mode": _(
                            "Rows with a quantity above 1 exist. Reduce them before switching to individual items."
                        )
                    }
                )


class MaterialItemQuerySet(models.QuerySet["MaterialItem"]):
    """Reusable filters for material items."""

    def with_product_id(self) -> MaterialItemQuerySet:
        """Annotate each item with the ID of the product it belongs to (PRD-003).

        The product named on the item wins; otherwise the product of the
        model applies. The annotation is called ``effective_product_id``.
        """
        return self.annotate(effective_product_id=Coalesce("product_override_id", "material_model__default_product_id"))

    def for_product(self, product_id: int) -> MaterialItemQuerySet:
        """Items that belong to the given product.

        Written as "names the product itself, or names none and its model
        leads to it" instead of comparing the annotation of
        :meth:`with_product_id`: the meaning is the same, but this form can
        use the indexes, the other one reads every item (NFA-012).
        """
        return self.filter(
            Q(product_override_id=product_id)
            | Q(product_override__isnull=True, material_model__default_product_id=product_id)
        )

    def without_product(self) -> MaterialItemQuerySet:
        """Items that cannot be planned because no product is assigned (PRD-005)."""
        return self.filter(product_override__isnull=True, material_model__default_product__isnull=True)

    def with_product(self) -> MaterialItemQuerySet:
        """The opposite of :meth:`without_product`."""
        return self.filter(Q(product_override__isnull=False) | Q(material_model__default_product__isnull=False))

    def with_category_fields(self) -> MaterialItemQuerySet:
        """Load the category-specific fields of all items with a few queries (MAT-009).

        The value shown for an item ("5 m") is formatted by the first field
        of its category, or of the nearest parent category that defines
        fields. Looked up row by row that is one query or more per item of a
        list; this fetches the fields of the categories and of two levels of
        parents for the whole list at once.
        """
        return self.prefetch_related(*(f"material_model__{path}" for path in CATEGORY_FIELD_PATHS))

    def operational(self) -> MaterialItemQuerySet:
        """Items that are fit for use (MAT-021)."""
        return self.filter(status__in=OPERATIONAL_STATUSES)

    def not_archived(self) -> MaterialItemQuerySet:
        """Everything except retired, sold and lost items (MAT-022)."""
        return self.exclude(status__in=ARCHIVED_STATUSES)


class MaterialItem(AuditedModel):
    """One physical piece of material; the "item" level of MAT-001 and MAT-011.

    Inventory ID
        ``inventory_number`` is the system-wide unique ID of MAT-003. It is
        stored as a number so that sorting follows the numeric value; the
        leading zeros are added for display (``0042``, see ``display_id``).

    Installed in (MAT-033 to MAT-041)
        ``installed_in`` points to the item this item sits in. Two kinds:
        *fixed* items always travel with their container, are not plannable
        on their own and do not count towards the free stock of their own
        product. *Loose* items count as planned whenever the container is
        planned and are free otherwise. ``individually_rentable`` makes a
        fixed item behave like a loose one (MAT-041).

    Bulk material (MAT-005)
        For models with ``tracking_mode = bulk`` a row stands for
        ``quantity`` pieces.

    Status (MAT-020, MAT-044, MAT-045)
        ``status_reason`` holds what was said when the status was last
        changed. Setting an item to "defective" needs a reason – whoever
        repairs it must know what to look for. A defective item can only go
        on to "in repair", "retired" or "sold". Both rules are checked in
        :meth:`clean`, so the page, the API and the import obey them alike.
        The change log keeps every status with its reason (MAT-025).
    """

    inventory_number = models.PositiveIntegerField(
        _("ID"),
        unique=True,
        error_messages={"unique": _("This ID is already taken.")},
    )
    material_model = models.ForeignKey(
        MaterialModel, verbose_name=_("material model"), on_delete=models.PROTECT, related_name="items"
    )
    product_override = models.ForeignKey(
        Product,
        verbose_name=_("different product"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="override_items",
        help_text=_("Only if this item belongs to a different product than its model."),
    )
    installed_in = models.ForeignKey(
        "self",
        verbose_name=_("installed in"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="contents",
    )
    connection_type = models.CharField(
        _("kind of connection"), max_length=10, choices=ConnectionType.choices, default=ConnectionType.FIXED
    )
    individually_rentable = models.BooleanField(
        _("can be rented on its own"),
        default=False,
        help_text=_("For permanently installed items that are taken out when needed."),
    )
    serial_number = models.CharField(_("serial number"), max_length=120, blank=True)
    note = models.TextField(_("note"), blank=True)
    # MAT-050: the date of the invoice and its number.
    purchase_date = models.DateField(_("invoice date"), null=True, blank=True)
    #: Partial purchase date: how much of ``purchase_date`` is known – "day", "month" or "year". For the last two
    #: the date is the first day of the period (``material.partial_dates``); without a date it is "day".
    purchase_date_precision = models.CharField(
        _("precision of the invoice date"),
        max_length=5,
        choices=[("day", _("day")), ("month", _("month")), ("year", _("year"))],
        default="day",
        help_text=_("Of an old item the day or the month of the purchase may be unknown."),
    )
    invoice_number = models.CharField(_("invoice number"), max_length=60, blank=True)
    purchase_note = models.CharField(_("purchase note"), max_length=250, blank=True)
    purchase_price = models.DecimalField(
        _("purchase price (net)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    # MAT-054: bought as a set – the price of the whole set is noted at one item ("head"), the others
    # point to it and have no price of their own. One level only: the head is never part of another set.
    purchase_price_in = models.ForeignKey(
        "self",
        verbose_name=_("price included in"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_set_members",
        help_text=_(
            "Bought as a set: the item whose purchase price includes this one. It then has no price of its own."
        ),
    )
    supplier = models.ForeignKey(
        Supplier,
        verbose_name=_("bought from"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_items",
    )
    supplier_article_number = models.CharField(_("supplier's article number"), max_length=120, blank=True)
    status = models.CharField(_("status"), max_length=12, choices=ItemStatus.choices, default=ItemStatus.AVAILABLE)
    status_reason = models.CharField(
        _("reason for the status"),
        max_length=250,
        blank=True,
        help_text=_("Why the item has its current status, e.g. what is defective."),
    )
    storage_location = models.ForeignKey(
        StorageLocation,
        verbose_name=_("storage location"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_items",
    )
    # MAT-080: the place within the storage location, e.g. "01-A-1" (shelf, bay, height).
    storage_spot = models.CharField(
        _("storage spot"),
        max_length=SPOT_LENGTH,
        blank=True,
        help_text=_("The place in the storage location, e.g. 01-A-1: shelf or area, bay (letter), height."),
    )
    quantity = models.PositiveIntegerField(
        _("quantity"), default=1, help_text=_("Only for bulk material; individual items always count 1.")
    )
    # MAT-013: what this item has different from its model, e.g. after a modification.
    specification_override = models.TextField(
        _("own description"),
        blank=True,
        help_text=_("Only if this item differs from its model, e.g. after a modification."),
    )
    field_value_overrides = models.JSONField(_("own category-specific values"), default=dict, blank=True)
    # MAT-077: a protection class of its own, e.g. after a modification; empty: that of its model.
    protection_class_override = models.CharField(
        _("own protection class"),
        max_length=3,
        choices=ProtectionClass.choices,
        blank=True,
        help_text=_("Only if this item differs from its model."),
    )
    # MAT-043: where a loose item was taken out of, so that it can be put back in one step.
    taken_out_of = models.ForeignKey(
        "self",
        verbose_name=_("taken out of"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    # Incoming invoices: what the item cost to acquire and how it is written off. Filled when the item is
    # booked in from an incoming invoice; empty for every other item. The date of acquisition is ``purchase_date``
    # (the invoice date), the price without ancillary cost ``purchase_price``. For bulk material (one row, many
    # pieces) all amounts are those of the whole row, as ``purchase_price`` is (MAT-005).
    asset_kind = models.CharField(
        _("kind of asset"),
        max_length=12,
        choices=AssetKind.choices,
        blank=True,
        help_text=_("Merchandise, low-value asset (GWG) or fixed asset. Empty: not classified."),
    )
    useful_life_months = models.PositiveSmallIntegerField(
        _("useful life (months)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(600)],
        help_text=_("For a fixed asset: the months it is written off over."),
    )
    ancillary_cost_net = models.DecimalField(
        _("ancillary acquisition cost (net)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("The share of transport, packaging, customs … of the invoice that fell to this item."),
    )
    acquisition_cost_net = models.DecimalField(
        _("acquisition cost (net)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Purchase price plus the share of the ancillary costs."),
    )
    source_position = models.ForeignKey(
        "incoming.InvoicePosition",
        verbose_name=_("incoming invoice position"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items",
        editable=False,
    )
    #: The pieces this item stood for when it was booked in from an invoice position – for a bulk
    #: row its quantity then. The quantity of the row goes down by building in and selling; this number does not, so
    #: "how much of the position is booked" stays right. ``None``: not made from an invoice, or before this field.
    source_quantity = models.PositiveIntegerField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    objects = MaterialItemQuerySet.as_manager()

    audit_sensitive = {
        "purchase_price": SpecialRight.PURCHASE_PRICES,
        "ancillary_cost_net": SpecialRight.PURCHASE_PRICES,
        "acquisition_cost_net": SpecialRight.PURCHASE_PRICES,
    }

    class Meta:
        verbose_name = _("material item")
        verbose_name_plural = _("material items")
        ordering = ["inventory_number"]
        indexes = [
            models.Index(fields=["status"], name="item_status_idx"),
            models.Index(fields=["serial_number"], name="item_serial_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.display_id} {self.material_model.display_short_name}"

    def audit_parent(self) -> models.Model | None:
        """Show item changes in the history of the material model as well."""
        return self.material_model

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the item; the acquisition cost follows an edited purchase price (R1-12).

        ``book_values.cost_of`` prefers ``acquisition_cost_net`` to price plus ancillary cost. When the purchase price is
        edited (item form, API, import) and the acquisition cost was the sum of price and share before and is not
        changed in the same step, the acquisition cost is worked out anew, so the books do not keep the old price.
        """
        before = None if self._state.adding else self._audit_before()
        if before is not None and "purchase_price" in before and self._follow_purchase_price(before):
            fields = kwargs.get("update_fields")
            if fields is not None and "acquisition_cost_net" not in fields:
                kwargs["update_fields"] = [*fields, "acquisition_cost_net"]
        super().save(*args, **kwargs)

    def _follow_purchase_price(self, before: dict[str, Any]) -> bool:
        """Recompute the acquisition cost after an edited price; returns whether it was changed."""

        def amount(name: str) -> Decimal | None:
            value = before.get(name)
            return None if value in (None, "") else Decimal(str(value))

        old_price, old_share, old_cost = (
            amount("purchase_price"),
            amount("ancillary_cost_net"),
            amount("acquisition_cost_net"),
        )
        if self.purchase_price is None or old_price is None or old_cost is None or self.purchase_price == old_price:
            return False
        if self.acquisition_cost_net != old_cost or old_cost != old_price + (old_share or Decimal("0")):
            return False  # the cost was set on purpose (or in this step): leave it
        total = self.purchase_price + (self.ancillary_cost_net or Decimal("0"))
        if not Decimal("0") <= total < Decimal("100000000"):
            return False  # does not fit the field: the person has to say what the cost is
        self.acquisition_cost_net = total
        return True

    # --- Identification -----------------------------------------------------

    @property
    def display_id(self) -> str:
        """The inventory ID with leading zeros, e.g. ``0042`` (MAT-003)."""
        from rentalars.material.numbering import format_inventory_number

        return format_inventory_number(self.inventory_number)

    # --- Product ------------------------------------------------------------

    @property
    def product(self) -> Product | None:
        """The product this item belongs to (PRD-003, PRD-004)."""
        return self.product_override or self.material_model.default_product

    # --- What the item has from its model (MAT-013) ----------------------------

    @property
    def effective_specification(self) -> str:
        """The item's own specification, or that of its model."""
        return self.specification_override or self.material_model.specification

    @property
    def effective_protection_class(self) -> str:
        """The protection class of the item: its own, else that of its model; empty if neither has one (MAT-077)."""
        return self.protection_class_override or self.material_model.protection_class

    @property
    def category_specific_display(self) -> str:
        """The first category-specific value, the item's own one first (MAT-011 no. 5, MAT-013)."""
        field = self.material_model.category.primary_field
        if field is not None and (self.field_value_overrides or {}).get(str(field.pk)):
            return field.display_value(self.field_value_overrides[str(field.pk)])
        return self.material_model.category_specific_display

    def field_rows(self) -> list[tuple[Any, str, bool]]:
        """All category-specific fields with their value and whether the item has its own (MAT-010, MAT-013)."""
        overrides = self.field_value_overrides or {}
        rows = []
        for field in self.material_model.category.applicable_fields():
            own = bool(overrides.get(str(field.pk)))
            rows.append((field, self.material_model.field_display(field, overrides), own))
        return rows

    def set_field_override(self, field: Any, raw_value: Any) -> None:
        """Give the item its own value for a category-specific field; empty removes it (MAT-013).

        Raises:
            ValidationError: The value does not fit the type of the field.
        """
        cleaned = field.clean_value(raw_value)
        values = dict(self.field_value_overrides or {})
        if cleaned and cleaned != self.material_model.field_values.get(str(field.pk), ""):
            values[str(field.pk)] = cleaned
        else:
            values.pop(str(field.pk), None)
        self.field_value_overrides = values

    # --- Where it is (MAT-018, MAT-038) ----------------------------------------

    @property
    def effective_storage_location(self) -> StorageLocation | None:
        """Where the item is kept: an installed item is where its outermost container is (MAT-038)."""
        seen = {self.pk}
        current: MaterialItem = self
        while current.installed_in_id is not None and current.installed_in_id not in seen:
            seen.add(current.installed_in_id)
            current = current.installed_in  # type: ignore[assignment]
        return current.storage_location

    @property
    def effective_storage_spot(self) -> str:
        """The spot within the location: an installed item has the spot of its outermost container (MAT-038, MAT-080)."""
        seen = {self.pk}
        current: MaterialItem = self
        while current.installed_in_id is not None and current.installed_in_id not in seen:
            seen.add(current.installed_in_id)
            current = current.installed_in  # type: ignore[assignment]
        return current.storage_spot

    # --- Status and connection ---------------------------------------------

    @property
    def is_operational(self) -> bool:
        """Whether the item is fit for use (MAT-021)."""
        return self.status in OPERATIONAL_STATUSES

    @property
    def is_archived(self) -> bool:
        """Whether the item is retired, sold or lost (MAT-022)."""
        return self.status in ARCHIVED_STATUSES

    @property
    def stored_status(self) -> str | None:
        """The status the item had when it was loaded or last saved; ``None`` for a new item.

        The change log keeps the loaded values to compare against
        (``AuditedModel``); reading them here costs no query.
        """
        before = self._audit_before()
        return before.get("status") if before else None

    @property
    def selectable_statuses(self) -> list[tuple[str, str]]:
        """The statuses a person may choose next, as ``(value, label)`` (MAT-045).

        From "defective" the way leads to repair or out of the stock; from
        every other status all others can be chosen.
        """
        current = self.stored_status or self.status
        if current == ItemStatus.DEFECTIVE:
            return [(status, str(ItemStatus(status).label)) for status in STATUSES_AFTER_DEFECTIVE]
        return [(value, str(label)) for value, label in SELECTABLE_STATUS_CHOICES if value != current]

    @property
    def is_installed(self) -> bool:
        """Whether the item sits in another item."""
        return self.installed_in_id is not None

    @property
    def travels_only_with_container(self) -> bool:
        """Fixed and not individually rentable: never plannable on its own (MAT-036)."""
        return self.is_installed and self.connection_type == ConnectionType.FIXED and not self.individually_rentable

    @property
    def is_planned_with_container(self) -> bool:
        """Loose (or fixed but rentable): occupied whenever the container is planned (MAT-036, MAT-041)."""
        return self.is_installed and not self.travels_only_with_container

    @property
    def purchase_date_text(self) -> str:
        """The date of purchase as shown: ``12.05.2015``, ``05.2015`` or ``2015``; "" without one."""
        return partial_dates.display(self.purchase_date, self.purchase_date_precision)

    @property
    def purchase_date_iso(self) -> str:
        """The date of purchase in ISO form with zeros for the unknown: ``2015-05-12``, ``2015-00-00``; "" without one."""
        return partial_dates.iso_text(self.purchase_date, self.purchase_date_precision)

    # --- Validation ---------------------------------------------------------

    #: Set by the import of items on the item it flags; only then may the status become "import error".
    by_import = False

    def clean(self) -> None:
        """Apply the rules for quantities and for "installed in" (MAT-034)."""
        super().clean()
        if (
            self.status == ItemStatus.IMPORT_ERROR
            and self.stored_status != ItemStatus.IMPORT_ERROR
            and not self.by_import
        ):
            raise ValidationError({"status": _("The status “import error” is only reached through the import.")})
        self.serial_number = (self.serial_number or "").strip()
        self.storage_spot = normalise_spot(self.storage_spot)  # MAT-080: "1a1" is "01-A-1"
        errors: dict[str, Any] = {}

        if self.material_model_id is not None:
            if self.protection_class_override == self.material_model.protection_class:
                # MAT-077: the same as the model is no class of its own – it follows the model, as MAT-013.
                self.protection_class_override = ""
            if not self.material_model.is_bulk and self.quantity != 1:
                errors["quantity"] = _("Individual items always have the quantity 1.")
            if self.material_model.is_bulk and self.installed_in_id is not None:
                errors["installed_in"] = _("Bulk material cannot be installed in another item.")

        if self.installed_in_id is None:
            # Without a container the connection details have no meaning.
            self.connection_type = ConnectionType.FIXED
            self.individually_rentable = False
        else:
            problem = self._installation_problem()
            if problem:
                errors["installed_in"] = problem
            if self.connection_type == ConnectionType.LOOSE:
                # "Individually rentable" is the exception for fixed items only.
                self.individually_rentable = False

        # Partial purchase date: the date is the first day of the period that is known.
        self.purchase_date, self.purchase_date_precision = partial_dates.normalised(
            self.purchase_date, self.purchase_date_precision
        )
        self._clean_status_change(errors)
        self._clean_purchase_set(errors)

        if self.pk is not None and self.is_archived and self.contents.exists():
            # MAT-040: the contents would vanish from view together with
            # their container. This lives here, not in a service, so that
            # the form, the API and the import all obey it.
            errors["status"] = _("Other items are still installed in %(id)s. Remove them before archiving it.") % {
                "id": self.display_id
            }
        if self.pk is not None and self.is_archived and self.installed_quantities.exists():
            # MAT-040 (built-in quantity material): the bulk material built into it would vanish with it.
            errors["status"] = _("Bulk material is still built into %(id)s. Take it out before archiving it.") % {
                "id": self.display_id
            }
        elif self.pk is not None and self.is_archived and self.installations.exists():
            errors["status"] = _("%(id)s is still built into other items. Take it out of them before archiving it.") % {
                "id": self.display_id
            }

        if errors:
            raise ValidationError(errors)

    def _clean_status_change(self, errors: dict[str, Any]) -> None:
        """Apply the rules for changing the status (MAT-044, MAT-045).

        Only a *change* is judged: an item that is created or imported as
        defective is taken as it is, and saving a defective item again –
        with a new note, say – asks no questions.
        """
        self.status_reason = (self.status_reason or "").strip()
        previous = self.stored_status
        if previous is None or previous == self.status:
            return
        if previous == ItemStatus.DEFECTIVE and self.status not in STATUSES_AFTER_DEFECTIVE:
            allowed = ", ".join(
                _("“%(name)s”") % {"name": ItemStatus(status).label} for status in STATUSES_AFTER_DEFECTIVE
            )
            errors["status"] = _("A defective item can only be set to %(allowed)s.") % {"allowed": allowed}
        elif self.status == ItemStatus.DEFECTIVE and not self.status_reason:
            errors["status_reason"] = _("Say what is defective. The reason is required for “defective”.")

    def _clean_purchase_set(self, errors: dict[str, Any]) -> None:
        """MAT-054: an item whose price is included in another has none of its own, and sets have one level.

        The head of a set carries the price of all its items. It cannot be
        part of another set itself, and an item that is the head of a set
        cannot have its price included somewhere else – the price would be
        counted twice or not at all.
        """
        head = self.purchase_price_in
        if head is None:
            return
        if self.pk is not None and head.pk == self.pk:
            errors["purchase_price_in"] = _("The price of an item cannot be included in its own price.")
            return
        if head.purchase_price_in_id is not None:
            errors["purchase_price_in"] = _(
                "The price of %(head)s is itself included in %(other)s. Name %(other)s instead."
            ) % {"head": head.display_id, "other": head.purchase_price_in.display_id}
            return
        if self.pk is not None and self.purchase_set_members.exists():
            errors["purchase_price_in"] = _(
                "The prices of other items are included in this one; it cannot be part of another set itself."
            )
            return
        if self.purchase_price is not None:
            errors["purchase_price"] = _(
                "The price of this item is included in %(head)s. Leave its own purchase price empty."
            ) % {"head": head.display_id}

    @property
    def purchase_set(self) -> list[MaterialItem]:
        """MAT-054: all items of the set this item was bought in, the head first; empty if it was bought alone."""
        head = self.purchase_price_in or self
        members = list(head.purchase_set_members.order_by("inventory_number")) if head.pk else []
        return [head, *members] if members else []

    def _installation_problem(self) -> str | None:
        """Return why the chosen container is not allowed, or ``None`` (MAT-034)."""
        container = self.installed_in
        if container is None:
            return None
        if self.pk is not None and container.pk == self.pk:
            return str(_("An item cannot be installed in itself."))
        if container.is_archived:
            return str(_("The item %(id)s is archived and cannot contain other items.") % {"id": container.display_id})
        if container.material_model.is_bulk:
            return str(_("Bulk material cannot contain other items."))
        # Walk up from the container. Meeting this item again would be a circle:
        # "0500 installed in 0310" while 0310 is installed in 0500.
        seen: set[int] = set()
        current: MaterialItem | None = container
        while current is not None and current.pk not in seen:
            if self.pk is not None and current.pk == self.pk:
                return str(
                    _("Circular reference: %(container)s is itself installed in %(item)s.")
                    % {"container": container.display_id, "item": self.display_id}
                )
            seen.add(current.pk)
            current = current.installed_in
        return None


# --- Files of models and items (MAT-017) --------------------------------------------------------


class MaterialFileKind(models.TextChoices):
    """What a file of a model or item is."""

    PICTURE = "picture", _("picture")  # MAT-090: the photos of a model or item; shown in German as "Foto"
    MANUAL = "manual", _("manual")
    INVOICE = "invoice", _("invoice")
    PROTOCOL = "protocol", _("inspection protocol")
    OTHER = "other", _("other")


def material_file_path(instance: MaterialFile, filename: str) -> str:
    """Store files of material in a folder per model, under a random name (see ``project_file_path``)."""
    import secrets
    from pathlib import Path

    extension = Path(filename).suffix.lower()[:10]
    model_id = instance.material_model_id or (instance.item.material_model_id if instance.item_id else 0)
    return f"material/{model_id}/{secrets.token_hex(12)}{extension}"


class MaterialFile(AuditedModel):
    """A picture or document of a material model or of a single item (MAT-017).

    Exactly one of ``material_model`` and ``item`` is set: a manual belongs
    to the model and applies to all its items; the invoice of one purchase
    belongs to the item.
    """

    material_model = models.ForeignKey(
        MaterialModel,
        verbose_name=_("material model"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="files",
    )
    item = models.ForeignKey(
        MaterialItem, verbose_name=_("item"), null=True, blank=True, on_delete=models.CASCADE, related_name="files"
    )
    kind = models.CharField(_("kind"), max_length=10, choices=MaterialFileKind.choices, default=MaterialFileKind.OTHER)
    title = models.CharField(_("title"), max_length=200, blank=True)
    file = models.FileField(_("file"), upload_to=material_file_path, max_length=200)
    #: MAT-090: the preview of a photo (JPEG, 640 pixels); empty for documents and for older pictures.
    thumbnail = models.FileField(_("preview"), upload_to=material_file_path, blank=True, max_length=200)
    original_name = models.CharField(_("file name"), max_length=255)
    size = models.PositiveBigIntegerField(_("size"), default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    uploaded_at = models.DateTimeField(_("uploaded"), default=timezone.now, editable=False)

    audit_exclude = frozenset({"file", "thumbnail", "size"})

    class Meta:
        verbose_name = _("material file")
        verbose_name_plural = _("material files")
        ordering = ["kind", "-uploaded_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(material_model__isnull=False, item__isnull=True)
                | Q(material_model__isnull=True, item__isnull=False),
                name="material_file_one_owner",
            )
        ]

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """The title, or the file name."""
        return self.title or self.original_name

    @property
    def is_picture(self) -> bool:
        """Whether the file can be shown as a picture."""
        return self.original_name.lower().rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "gif", "webp"}

    def audit_parent(self) -> models.Model | None:
        """Show file changes in the history of the model or item."""
        return self.item if self.item_id else self.material_model


# --- Blocked periods (MAT-024) -----------------------------------------------------------------


class ItemBlock(AuditedModel):
    """A period in which an item cannot be planned, e.g. "in repair until 15 November" (MAT-024).

    During the period the item does not count as free: the availability of
    its product is one piece lower (``availability.engine``). Its status is
    not touched; a block is a plan for the future, a status is the state of
    today.
    """

    item = models.ForeignKey(MaterialItem, verbose_name=_("item"), on_delete=models.CASCADE, related_name="blocks")
    start = models.DateTimeField(_("from"))
    end = models.DateTimeField(_("until"))
    reason = models.CharField(_("reason"), max_length=250)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("blocked period")
        verbose_name_plural = _("blocked periods")
        ordering = ["start", "id"]
        indexes = [models.Index(fields=["start", "end"], name="item_block_period_idx")]

    def __str__(self) -> str:
        return f"{self.item.display_id}: {self.reason}"

    def audit_parent(self) -> models.Model | None:
        """Show blocks in the history of the item."""
        return self.item

    def clean(self) -> None:
        """A block ends after it starts and has a reason."""
        super().clean()
        self.reason = (self.reason or "").strip()
        if self.start and self.end and self.end <= self.start:
            raise ValidationError({"end": _("The end must lie after the start.")})
        if not self.reason:
            raise ValidationError({"reason": _("Say why the item is blocked.")})


# --- Defect reports (MAT-023) -----------------------------------------------------------------


def defect_photo_path(instance: DefectReport, filename: str) -> str:
    """Store photos of defects in a folder per item, under a random name."""
    import secrets
    from pathlib import Path

    extension = Path(filename).suffix.lower()[:10]
    return f"defects/{instance.item_id}/{secrets.token_hex(12)}{extension}"


class DefectReport(models.Model):
    """What somebody found broken, with a photo if there is one (MAT-023).

    A report sets the item to "defective" with the description as reason
    and tells the warehouse (``material.services.report_defect``). It stays
    as a record of what was found, also after the repair. ``context`` says
    where it was found, e.g. "on return from project 2027-0042".
    """

    item = models.ForeignKey(
        MaterialItem, verbose_name=_("item"), on_delete=models.CASCADE, related_name="defect_reports"
    )
    description = models.TextField(_("what is defective"))
    photo = models.ImageField(_("photo"), upload_to=defect_photo_path, blank=True, max_length=200)
    context = models.CharField(_("found"), max_length=250, blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    reported_at = models.DateTimeField(_("reported"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("defect report")
        verbose_name_plural = _("defect reports")
        ordering = ["-reported_at", "-id"]

    def __str__(self) -> str:
        return f"{self.item.display_id}: {self.description[:60]}"


# --- Inspections (MAT-030 to MAT-032) ----------------------------------------------------------


class InspectionType(AuditedModel):
    """A recurring inspection, e.g. "electrical test every 12 months" (MAT-030).

    It applies to all items of the chosen models and of the models of the
    chosen categories – including their subcategories.
    """

    name = models.CharField(_("name"), max_length=120, unique=True)
    interval_months = models.PositiveSmallIntegerField(
        _("interval (months)"), default=12, validators=[MinValueValidator(1)]
    )
    description = models.TextField(_("description"), blank=True, help_text=_("What is checked, which standard."))
    categories = models.ManyToManyField(
        Category, verbose_name=_("categories"), blank=True, related_name="inspection_types"
    )
    material_models = models.ManyToManyField(
        MaterialModel, verbose_name=_("material models"), blank=True, related_name="inspection_types"
    )
    is_active = models.BooleanField(_("active"), default=True)
    # MAT-078: recording an inspection of this type asks for the measured values (material.dguv).
    is_electrical = models.BooleanField(
        _("electrical inspection (DGUV V3 / DIN VDE 0701-0702)"),
        default=False,
        help_text=_(
            "Recording asks for visual inspection, protective conductor and insulation resistance, leakage "
            "currents, function test and test device, checks the limits and suggests the result."
        ),
    )

    class Meta:
        verbose_name = _("inspection type")
        verbose_name_plural = _("inspection types")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class InspectionResult(models.TextChoices):
    """The outcome of an inspection (MAT-031)."""

    PASSED = "passed", _("passed")
    FAILED = "failed", _("failed")


def inspection_protocol_path(instance: Inspection, filename: str) -> str:
    """Store protocols in a folder per item, under a random name."""
    import secrets
    from pathlib import Path

    extension = Path(filename).suffix.lower()[:10]
    return f"inspections/{instance.item_id}/{secrets.token_hex(12)}{extension}"


class Inspection(AuditedModel):
    """One inspection of one item (MAT-031).

    The next one is due ``interval_months`` after a passed inspection
    (``material.inspections``). A failed inspection sets the item to
    "defective"; it is due again at once – after the repair it is inspected
    anew.
    """

    item = models.ForeignKey(MaterialItem, verbose_name=_("item"), on_delete=models.CASCADE, related_name="inspections")
    inspection_type = models.ForeignKey(
        InspectionType, verbose_name=_("inspection"), on_delete=models.PROTECT, related_name="inspections"
    )
    date = models.DateField(_("date"))
    inspector = models.CharField(_("inspected by"), max_length=120)
    result = models.CharField(_("result"), max_length=10, choices=InspectionResult.choices)
    note = models.TextField(_("note"), blank=True)
    protocol = models.FileField(_("protocol"), upload_to=inspection_protocol_path, blank=True, max_length=200)
    protocol_name = models.CharField(_("file name"), max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    recorded_at = models.DateTimeField(_("recorded"), default=timezone.now, editable=False)
    # MAT-078: what an electrical inspection measured (InspectionType.is_electrical); the limits and
    # verdicts follow from ``material.dguv``. Empty for other inspections; a value is empty where it was not
    # measured or does not apply to the protection class.
    protection_class = models.CharField(
        _("protection class"), max_length=3, choices=ProtectionClass.choices, blank=True
    )
    test_device = models.CharField(_("test device"), max_length=120, blank=True)
    visual_check_passed = models.BooleanField(_("visual inspection passed"), null=True, blank=True)
    cord_length_m = models.DecimalField(
        _("cord length (m)"), max_digits=6, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    pe_resistance_ohm = models.DecimalField(
        _("protective conductor resistance (Ω)"),
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    insulation_resistance_mohm = models.DecimalField(
        _("insulation resistance (MΩ)"),
        max_digits=9,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    pe_current_ma = models.DecimalField(
        _("protective conductor current (mA)"),
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    touch_current_ma = models.DecimalField(
        _("touch current (mA)"),
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    function_test_passed = models.BooleanField(_("function test passed"), null=True, blank=True)

    audit_exclude = frozenset({"protocol"})

    class Meta:
        verbose_name = _("inspection")
        verbose_name_plural = _("inspections")
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["item", "inspection_type", "date"], name="inspection_latest_idx")]

    def __str__(self) -> str:
        return f"{self.item.display_id}: {self.inspection_type} {self.date:{local_pattern('%d.%m.%Y')}}"

    def audit_parent(self) -> models.Model | None:
        """Show inspections in the history of the item."""
        return self.item

    @property
    def passed(self) -> bool:
        """Whether the item passed."""
        return self.result == InspectionResult.PASSED

    @property
    def is_electrical(self) -> bool:
        """Whether this was an electrical inspection with measured values (MAT-078); it always names its class."""
        return bool(self.protection_class)

    @cached_property
    def evaluation(self) -> Any:
        """The measured values with their limits and verdicts (``material.dguv.Evaluation``); ``None`` if not electrical."""
        from rentalars.material.dguv import evaluate_inspection

        return evaluate_inspection(self) if self.is_electrical else None


class Vehicle(AuditedModel):
    """LOG-002, LOG-003: what makes an item of a vehicle product a vehicle of the fleet.

    A vehicle or trailer is an item of a material model whose product is a
    vehicle (``ProductKind.VEHICLE``): it has its ID, status, files,
    inspections (main inspection, DGUV/UVV – LOG-014), defects and label
    like any item. Its rates are those of the product (LOG-005); this table
    holds what belongs to the vehicle itself:

    * the licence plate, unique among the vehicles,
    * for a motor vehicle the seats as minimum and maximum (LOG-003) – for
      removable or variably fitted seats; both the same for a fixed number,
    * the driving licence class it needs (LOG-012) – for a trailer the class
      of the combination,
    * how much a motor vehicle may tow (LOG-013; 0: it may not tow) and the
      permissible total weight, of a trailer in particular.

    The row is made when the vehicle's data are first saved; an item of a
    vehicle product without it simply has no data yet.
    """

    item = models.OneToOneField(MaterialItem, verbose_name=_("item"), on_delete=models.CASCADE, related_name="vehicle")
    licence_plate = models.CharField(_("licence plate"), max_length=20, blank=True)
    seats_min = models.PositiveSmallIntegerField(
        _("seats min."), null=True, blank=True, validators=[MinValueValidator(1)]
    )
    seats_max = models.PositiveSmallIntegerField(
        _("seats max."), null=True, blank=True, validators=[MinValueValidator(1)]
    )
    licence_class = models.CharField(
        _("driving licence class"),
        max_length=12,
        blank=True,
        help_text=_("For example B, BE, C1. For a trailer: the class of the combination."),
    )
    towing_capacity_kg = models.PositiveIntegerField(
        _("towing capacity (kg)"), null=True, blank=True, help_text=_("Only for motor vehicles. 0: may not tow.")
    )
    gross_weight_kg = models.PositiveIntegerField(_("permissible total weight (kg)"), null=True, blank=True)

    class Meta:
        verbose_name = _("vehicle")
        verbose_name_plural = _("vehicles")
        # A licence plate belongs to one vehicle – a rule of ``clean``, not a constraint: an empty plate may repeat,
        # and MariaDB has no unique index with a condition (models.W036 on every command).

    def __str__(self) -> str:
        return self.licence_plate or self.item.display_id

    def audit_parent(self) -> models.Model | None:
        """Show changes in the history of the item."""
        return self.item

    @property
    def is_car(self) -> bool:
        """Whether the vehicle is a motor vehicle – from its product (LOG-005)."""
        product = self.item.product
        return product is not None and product.is_car

    def clean(self) -> None:
        """LOG-003: a motor vehicle has its seats, min. at most max.; a trailer has none and tows nothing."""
        super().clean()
        self.licence_plate = " ".join((self.licence_plate or "").upper().split())
        self.licence_class = (self.licence_class or "").strip().upper()
        errors: dict[str, Any] = {}
        if self.licence_plate and Vehicle.objects.filter(licence_plate=self.licence_plate).exclude(pk=self.pk).exists():
            errors["licence_plate"] = _("Another vehicle has this licence plate.")
        if self.item_id is not None and self.is_car:
            if self.seats_min is None:
                errors["seats_min"] = _("Enter the seats: min. and max., both the same for a fixed number.")
            if self.seats_max is None:
                errors["seats_max"] = _("Enter the seats: min. and max., both the same for a fixed number.")
            if self.seats_min and self.seats_max and self.seats_min > self.seats_max:
                errors["seats_min"] = _("The minimum of seats is at most the maximum.")
        elif self.item_id is not None:
            if self.seats_min is not None or self.seats_max is not None:
                errors["seats_min"] = _("Only a motor vehicle has seats.")
            if self.towing_capacity_kg is not None:
                errors["towing_capacity_kg"] = _("Only a motor vehicle tows.")
        if errors:
            raise ValidationError(errors)

    @property
    def seats_text(self) -> str:
        """The seats in short: "3" or "2–9" (LOG-003)."""
        if self.seats_min is None and self.seats_max is None:
            return ""
        if self.seats_min == self.seats_max or self.seats_min is None:
            return str(self.seats_max)
        return f"{self.seats_min}–{self.seats_max}"


# MAT-056: the company's texts and logo of the labels – a table of this module, in a file of its own.
# MAT-067, MAT-069: audits of items, their to-dos and Einstellungen → Audits – tables of this module, in a file of its own.
from rentalars.material.audit_models import AuditResult, AuditSettings, ItemAudit, ItemTodo  # noqa: E402, F401

# Built-in quantity material; MAT-040: bulk material built into an item – a table of this module, in a file of its own.
from rentalars.material.installed_models import InstalledQuantity  # noqa: E402, F401
from rentalars.material.label_settings import LabelKind, LabelSettings  # noqa: E402, F401

# isort: split
# Incoming invoices: the limit of a low-value asset and the usual useful life – a table of this module.
from rentalars.material.asset_models import AssetSettings  # noqa: E402, F401

# Depreciation, used sale from stock: the record of a sale out of the stock – a table of this module.
from rentalars.material.sale_models import SaleFromStock  # noqa: E402, F401
