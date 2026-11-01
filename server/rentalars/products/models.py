# SPDX-License-Identifier: GPL-3.0-or-later
"""Products: the units that are planned, rented and sold (chapter 5.3).

A product is what appears in a project ("6 × XLR cable 5 m"). Which physical
items are behind it is the business of the material module; several material
models of different manufacturers can feed one product (PRD-002).
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.masterdata.models import Category, RentalScale, TaxRate, Unit

#: PRD-008: at least one capital letter, a hyphen, at least three digits.
ARTICLE_NUMBER_PATTERN = re.compile(r"^[A-Z]+-[0-9]{3,}$")

#: PRD-012: a GTIN/EAN has one of these lengths.
GTIN_LENGTHS = frozenset({8, 12, 13, 14})


class ProductKind(models.TextChoices):
    """What a product is, which decides how stock and packing treat it."""

    RENTAL = "rental", _("rental product")  # PRD-019: returns to stock after the project
    SALE = "sale", _("sale or consumable")  # PRD-020: leaves stock for good
    # PRD-021, PRD-044: the price of a job function – one service product per function, planned only
    # through the crew planning, never as a material line.
    SERVICE = "service", _("service")
    KIT = "kit", _("kit")  # PRD-022: consists of other products
    SURCHARGE = "surcharge", _("surcharge")  # PRD-031: fixed amount or percentage
    SUBRENTAL = "subrental", _("subrental")  # PRD-040: material from a supplier
    # PRD-045: transport, travel costs, fees – no stock, not packed, planned like material.
    INCIDENTAL = "incidental", _("incidental costs")
    # LOG-002, LOG-005: a vehicle or trailer of the fleet – its items are the vehicles, its rates are per
    # kilometre (and per day for a trailer); planned under "Logistik", never as a material line.
    VEHICLE = "vehicle", _("vehicle")


class VehicleType(models.TextChoices):
    """LOG-002: what a vehicle product is – it decides how it is billed (LOG-005, LOG-006)."""

    CAR = "car", _("motor vehicle")
    TRAILER = "trailer", _("trailer")


class TrailerBilling(models.TextChoices):
    """LOG-005: how a trailer is billed – per day of the booking, or per kilometre."""

    DAY = "day", _("per day")
    KM = "km", _("per kilometre")


class BillingMode(models.TextChoices):
    """How the price of a project line is calculated (PRD-014, PRD-033)."""

    DAILY_PER_PIECE = "daily_piece", _("daily rental per piece")
    DAILY_PER_KIT = "daily_kit", _("daily rental per kit")
    FLAT = "flat", _("flat")
    HOURLY = "hourly", _("by the hour")
    EFFORT = "effort", _("by effort")

    @classmethod
    def daily_modes(cls) -> frozenset[str]:
        """The modes to which rental days and the rental scale apply."""
        return frozenset({cls.DAILY_PER_PIECE.value, cls.DAILY_PER_KIT.value})


class ScaleMode(models.TextChoices):
    """Which rental scale a product uses (PRD-034)."""

    INHERIT = "inherit", _("as the category or the default")
    CUSTOM = "custom", _("own scale")
    NONE = "none", _("no scale")


class SurchargeType(models.TextChoices):
    """The two kinds of surcharge (PRD-031)."""

    FIXED = "fixed", _("fixed amount")
    PERCENT = "percent", _("percentage")


#: Kinds whose products can physically be in the warehouse.
STOCK_KINDS = frozenset({ProductKind.RENTAL.value, ProductKind.SALE.value})

#: PRD-043: what customer material can be – it comes back after the project; a kit of the owner's products.
CUSTOMER_MATERIAL_KINDS = frozenset({ProductKind.RENTAL.value, ProductKind.KIT.value})

#: PRD-044: kinds that are planned only through the crew planning – never as material lines.
CREW_ONLY_KINDS = frozenset({ProductKind.SERVICE.value})

#: LOG-001: kinds planned only under "Logistik" – never as material lines, never packed or in a kit.
LOGISTICS_KINDS = frozenset({ProductKind.VEHICLE.value})

#: LOG-002: kinds whose products have material models and items – those with stock, and vehicles (their
#: items are the vehicles of the fleet, counted by the logistics, not by the availability of material).
MATERIAL_KINDS = STOCK_KINDS | LOGISTICS_KINDS

#: Billing mode preselected for a new product of each kind (PRD-014). A service is billed by the
#: hour (its crew lines then by effort, PER-036), and incidental costs flat (PRD-045).
DEFAULT_BILLING_MODE = {
    ProductKind.RENTAL.value: BillingMode.DAILY_PER_PIECE.value,
    ProductKind.KIT.value: BillingMode.DAILY_PER_KIT.value,
    ProductKind.SALE.value: BillingMode.FLAT.value,
    ProductKind.SERVICE.value: BillingMode.HOURLY.value,
    ProductKind.SURCHARGE.value: BillingMode.FLAT.value,
    ProductKind.SUBRENTAL.value: BillingMode.FLAT.value,
    ProductKind.INCIDENTAL.value: BillingMode.FLAT.value,
    # LOG-005: the day price of a trailer is a daily rental with the rental scale; a vehicle has its own rates.
    ProductKind.VEHICLE.value: BillingMode.DAILY_PER_PIECE.value,
}


def validate_gtin(value: str) -> None:
    """Check length and check digit of a GTIN/EAN (PRD-012).

    The last digit is a check digit. Counting from the right and skipping the
    check digit, the digits are weighted 3, 1, 3, 1 …; the check digit brings
    the weighted sum up to the next multiple of ten.

    Example: ``4006381333931`` – the weighted sum of the first twelve digits
    is 89, so the check digit must be 1.
    """
    if not (value.isascii() and value.isdigit()):
        raise ValidationError(_("A GTIN consists of digits only."))
    if len(value) not in GTIN_LENGTHS:
        raise ValidationError(_("A GTIN has 8, 12, 13 or 14 digits."))
    weighted_sum = 0
    for position, digit in enumerate(reversed(value[:-1])):
        weight = 3 if position % 2 == 0 else 1
        weighted_sum += int(digit) * weight
    expected_check_digit = (10 - weighted_sum % 10) % 10
    if expected_check_digit != int(value[-1]):
        raise ValidationError(_("The check digit of the GTIN is wrong."))


def validate_article_number_format(value: str) -> None:
    """Check an article number against the pattern of PRD-008."""
    if not ARTICLE_NUMBER_PATTERN.match(value):
        raise ValidationError(
            _("An article number consists of capital letters, a hyphen and at least three digits, for example K-005.")
        )


class Product(AuditedModel):
    """A plannable product with article number and prices (PRD-001, PRD-012).

    Products are what projects are planned with; the physical pieces behind
    them are material items (PRD-001, PRD-002).

    Prices
        ``price`` is the price for renting or performing one unit. How it is
        applied depends on ``billing_mode``; for rental products it is the
        daily rental price (PRD-013). ``sale_price`` is the price for selling
        one unit out of stock. A product has one
        price (PRD-047): a sale product its ``sale_price``, every other product its
        ``price``. What is sold is a sale product; project lines that sold a
        rental product before keep their own price (PRJ-015).

    Stock
        A product has no stock field. Its stock is counted from the material
        items assigned to it (PRD-006, see ``availability.stock``).
    """

    article_number = models.CharField(
        _("article number"),
        max_length=20,
        unique=True,
        validators=[validate_article_number_format],
        error_messages={"unique": _("This article number is already taken.")},
    )
    category = models.ForeignKey(
        Category, verbose_name=_("category"), on_delete=models.PROTECT, related_name="products"
    )
    gtin = models.CharField(_("GTIN/EAN"), max_length=14, blank=True, validators=[validate_gtin])
    name = models.CharField(_("name"), max_length=200, help_text=_("Appears on documents."))
    description = models.TextField(_("description"), blank=True)
    note = models.TextField(_("internal note"), blank=True, help_text=_("Never appears on customer documents."))
    unit = models.ForeignKey(Unit, verbose_name=_("unit"), on_delete=models.PROTECT, related_name="products")
    tax_rate = models.ForeignKey(TaxRate, verbose_name=_("tax rate"), on_delete=models.PROTECT, related_name="products")
    kind = models.CharField(_("product kind"), max_length=12, choices=ProductKind.choices, default=ProductKind.RENTAL)

    price = models.DecimalField(
        _("price (net)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("For rental products the price per day."),
    )
    sale_price = models.DecimalField(
        _("sale price (net)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    calculation_note = models.TextField(_("calculation note"), blank=True)
    billing_mode = models.CharField(
        _("billing mode"), max_length=20, choices=BillingMode.choices, default=BillingMode.DAILY_PER_PIECE
    )
    rental_scale_mode = models.CharField(
        _("rental scale"), max_length=10, choices=ScaleMode.choices, default=ScaleMode.INHERIT
    )
    rental_scale = models.ForeignKey(
        RentalScale,
        verbose_name=_("own rental scale"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="products",
    )
    surcharge_type = models.CharField(
        _("surcharge type"), max_length=10, choices=SurchargeType.choices, default=SurchargeType.FIXED
    )
    surcharge_percent = models.DecimalField(
        _("surcharge in percent"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1000"))],
    )

    # VFG-005: buffer times that differ from category and system default.
    buffer_before_hours = models.DecimalField(
        _("buffer before use (hours)"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Empty: as the category or the default."),
    )
    buffer_after_hours = models.DecimalField(
        _("buffer after use (hours)"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Empty: as the category or the default."),
    )

    # PRD-041: like the maximum discount of a job function (PER-026), for any product.
    max_discount_percent = models.DecimalField(
        _("maximum discount in percent"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=_(
            "No line of this product is discounted more – by its own discount, the customer's standard discount "
            "or its group's. 0: never discounted. Empty: no limit."
        ),
    )

    # PER-035: hour tiers per day – the hours of one day beyond the limit cost the higher price.
    hours_limit = models.DecimalField(
        _("limit in hours per day"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.25")), MaxValueValidator(Decimal("23.75"))],
        help_text=_(
            "Only for services billed by the hour: the hours of one day beyond this cost the price from the limit, "
            "e.g. 10 – from the 11th hour of a day. Empty: every hour costs the same."
        ),
    )
    price_above_limit = models.DecimalField(
        _("price per hour from the limit (net)"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    # PER-009: whether the crew lines of a service get the surcharges for night, Sunday and holidays.
    time_surcharges = models.BooleanField(
        _("surcharges for night, Sunday and holidays"),
        default=True,
        help_text=_(
            "Only for services billed by the hour. Off: crew lines of this service get no surcharges, "
            "neither on the price nor on the costs."
        ),
    )

    # --- LOG-002, LOG-005, LOG-006, LOG-010: the rates of a vehicle or trailer ---------------------
    vehicle_type = models.CharField(
        _("vehicle type"), max_length=10, choices=VehicleType.choices, blank=True, help_text=_("Only for vehicles.")
    )
    price_per_km = models.DecimalField(
        _("price per kilometre (net)"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("For a motor vehicle its rate; for a trailer the rate when it is billed per kilometre."),
    )
    trailer_surcharge_per_km = models.DecimalField(
        _("trailer surcharge per kilometre (net)"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Only for motor vehicles: added to the price per kilometre on trips with a trailer."),
    )
    trailer_billing = models.CharField(
        _("trailer billed"),
        max_length=4,
        choices=TrailerBilling.choices,
        default=TrailerBilling.DAY,
        help_text=_("Only for trailers: how a new booking is billed; it can be switched in the project."),
    )
    cost_per_km = models.DecimalField(
        _("internal cost per kilometre"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Fuel, wear, insurance – what a kilometre costs the company."),
    )
    cost_per_day = models.DecimalField(
        _("internal cost per day"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Only for trailers billed per day: what a day costs the company."),
    )

    # PRD-020: consumables are re-ordered when their stock falls below this.
    minimum_stock = models.PositiveIntegerField(
        _("minimum stock"),
        null=True,
        blank=True,
        help_text=_("For sale and consumable products: below this, the warehouse is warned. Empty: no warning."),
    )

    # (products of several pieces; PRD-052): "10 × XLR cable 1.5 m" is one product, K-005. Stock, planning and the
    # packlist count in products; every product stands for this many items of the material behind it.
    pieces_per_product = models.PositiveIntegerField(
        _("pieces per product"),
        default=1,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Of how many items of the material one piece of this product consists, e.g. 10 for a “10-pack”. "
            "Stock, planning and packing count in products; each one takes this many items from the stock."
        ),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Deactivated products stay visible in old projects but cannot be added to new ones."),
    )
    # PRD-043: customer material – the gear of a customer stored here. Protected: a customer whose material is
    # in the warehouse cannot be deleted by accident.
    owner = models.ForeignKey(
        "customers.Customer",
        verbose_name=_("owner"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="owned_products",
        help_text=_("Only for customer material: the customer it belongs to. It is planned only in their projects."),
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    audit_sensitive = {
        "price": SpecialRight.PRICES,
        "sale_price": SpecialRight.PRICES,
        "calculation_note": SpecialRight.PRICES,
        "surcharge_percent": SpecialRight.PRICES,
        "max_discount_percent": SpecialRight.PRICES,
        "price_above_limit": SpecialRight.PRICES,
        # LOG-005, LOG-010: the rates of a vehicle; its internal costs with the purchase prices (AUT-019).
        "price_per_km": SpecialRight.PRICES,
        "trailer_surcharge_per_km": SpecialRight.PRICES,
        "cost_per_km": SpecialRight.PURCHASE_PRICES,
        "cost_per_day": SpecialRight.PURCHASE_PRICES,
    }

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["article_number"]

    def __str__(self) -> str:
        return f"{self.article_number} {self.name}"

    # --- Validation ---------------------------------------------------------

    def clean(self) -> None:
        """Apply the rules for article number, prices and product kind."""
        super().clean()
        self.article_number = (self.article_number or "").strip().upper()
        self.gtin = (self.gtin or "").strip()
        errors: dict[str, Any] = {}
        self._check_article_number(errors)
        if self.category_id is not None and (self.owner_id is not None or self.category.holds_customer_material):
            self._check_customer_material(errors)
        else:
            self._check_prices(errors)
        self._check_owner_kept(errors)
        self._check_hour_tiers(errors)
        self._check_pieces(errors)
        self._check_service_kept(errors)
        self._check_vehicle_kept(errors)
        if self.rental_scale_mode == ScaleMode.CUSTOM and self.rental_scale_id is None:
            errors["rental_scale"] = _("Choose the scale this product should use.")
        if errors:
            raise ValidationError(errors)

    def _check_article_number(self, errors: dict[str, Any]) -> None:
        """PRD-008: the letter part must be the code of the product's category.

        The format itself is checked by the field validator. Here follows
        the part that needs the database: is there a category with this
        code, and is it the category of this product?
        """
        if not ARTICLE_NUMBER_PATTERN.match(self.article_number):
            return  # the field validator already reports the format error
        code = self.article_number.split("-", 1)[0]
        if not Category.objects.filter(parent__isnull=True, code=code).exists():
            errors["article_number"] = _("There is no category with the code %(code)s.") % {"code": code}
            return
        if self.category_id is not None and self.category.effective_code != code:
            errors["article_number"] = _(
                "The article number must start with %(expected)s, the code of the category %(category)s."
            ) % {"expected": self.category.effective_code, "category": self.category.main_category.name}

    def _check_customer_material(self, errors: dict[str, Any]) -> None:
        """PRD-043: customer material has an owner, sits in a category for it, and never has a price.

        It is a rental product (it comes back after the project) or a kit of
        the customer's own products. Billing mode and scale are set so that
        no amount can ever come out of it: billed flat, without a scale.
        """
        if not self.category.holds_customer_material:
            errors["owner"] = _(
                "Only products of a category for customer material belong to a customer. Choose such a category "
                "or leave the owner empty."
            )
            return
        if self.owner_id is None:
            errors["owner"] = _("Customer material belongs to a customer: choose the owner.")
        if self.kind not in CUSTOMER_MATERIAL_KINDS:
            errors["kind"] = _("Customer material is a rental product or a kit of the customer's products.")
        prices = {
            "price": self.price,
            "sale_price": self.sale_price,
            "surcharge_percent": self.surcharge_percent,
        }
        for name, value in prices.items():
            if value is not None:
                errors[name] = _("Customer material has no price.")
        self.billing_mode = BillingMode.FLAT
        self.rental_scale_mode = ScaleMode.NONE
        self.rental_scale = None
        self.max_discount_percent = None

    def _check_owner_kept(self, errors: dict[str, Any]) -> None:
        """PRD-043: once planned in projects, material keeps its owner – the projects are the owner's."""
        if self.pk is None or "owner" in errors:
            return
        stored = Product.objects.filter(pk=self.pk).values_list("owner_id", flat=True).first()
        if stored != self.owner_id and self.is_used_in_projects():
            errors["owner"] = _("This product is planned in projects already. Its owner can no longer be changed.")

    @property
    def is_customer_material(self) -> bool:
        """PRD-043: material of a customer, stored here; planned only in the owner's projects, never charged."""
        return self.owner_id is not None

    def _check_hour_tiers(self, errors: dict[str, Any]) -> None:
        """PER-035: a limit of hours per day with its price – only for services billed by the hour, both or none."""
        if self.hours_limit is None:
            if self.price_above_limit is not None:
                errors["hours_limit"] = _("Enter the limit from which the higher price applies.")
            return
        if self.kind != ProductKind.SERVICE:
            errors["hours_limit"] = _("Only services have a limit of hours per day.")
        elif self.billing_mode not in (BillingMode.HOURLY, BillingMode.EFFORT):
            errors["hours_limit"] = _("A limit of hours per day applies only to services billed by the hour.")
        elif self.price_above_limit is None:
            errors["price_above_limit"] = _("Enter the price per hour from the limit.")

    def _check_pieces(self, errors: dict[str, Any]) -> None:
        """(products of several pieces; PRD-052): only stock products consist of several pieces, and not while material is out.

        The quantities of lines, packlists and subrentals count products; a changed number of pieces would change
        what is meant by what is out or chosen. So it is refused as long as items of the product are chosen for a
        packlist or out; before and after that it is a plain setting.
        """
        pieces = self.pieces_per_product
        if pieces is None or pieces < 1:
            errors["pieces_per_product"] = _("A product consists of at least one piece.")
            return
        if pieces > 1 and self.kind not in STOCK_KINDS:
            errors["pieces_per_product"] = _("Only rental and sale products consist of several pieces.")
            return
        if self.pk is None:
            return
        stored = Product.objects.filter(pk=self.pk).values_list("pieces_per_product", flat=True).first()
        if stored is None or stored == pieces:
            return
        from rentalars.packing.models import Allocation, PackEntry

        in_packing = Allocation.objects.filter(entry__product_id=self.pk, returned_at__isnull=True).exists()
        if not in_packing:
            in_packing = PackEntry.objects.filter(
                product_id=self.pk,
                issued_quantity__gt=models.F("taken_back_quantity") + models.F("handed_over_quantity"),
            ).exists()
        if in_packing:
            errors["pieces_per_product"] = _(
                "Items of this product are chosen for a packing list or out. The number of pieces can be changed "
                "once everything is back."
            )
            return
        # (R3-8): lines that wish for more items than the new number of pieces holds. The planner
        # must trim those wishes first; otherwise the line could no longer be saved, and a copy would keep them.
        too_many = self._lines_with_too_many_wishes(pieces)
        if too_many:
            errors["pieces_per_product"] = _(
                "Lines wish for more items than %(pieces)d pieces hold: %(lines)s. Remove the extra wished items "
                "from these lines first."
            ) % {"pieces": pieces, "lines": too_many}
            return
        # (pieces per product; PRD-052): a line of a running project meant "3 × 1 piece"; with another number
        # it would mean something else without anyone having said so.
        from rentalars.projects.models import FINISHED_STATUSES

        planned = self.material_lines.exclude(project__status__in=FINISHED_STATUSES).count()
        if planned:
            errors["pieces_per_product"] = ngettext(
                "%(count)d line of a project that is not finished yet plans this product. The number of pieces can "
                "be changed once the project is finished or the line is removed.",
                "%(count)d lines of projects that are not finished yet plan this product. The number of pieces can "
                "be changed once the projects are finished or the lines are removed.",
                planned,
            ) % {"count": planned}

    def _lines_with_too_many_wishes(self, pieces: int, *, limit: int = 4) -> str:
        """The lines that wish for more items than ``pieces`` per product would allow, in words; empty if none (R3-8).

        ``2027-0003 (3 items, 2 pieces), 2027-0007 (4 items, 2 pieces) and others``; every project status counts: a
        finished project can be reopened or copied.
        """
        wishing = (
            self.material_lines.filter(preferred_item__isnull=False)
            .annotate(wished=models.Count("further_preferred_items") + 1)
            .filter(wished__gt=1)
            .select_related("project")
            .order_by("project__number", "position", "pk")
        )
        found = [
            str(_("%(project)s (%(items)d items, %(pieces)d pieces)"))
            % {
                "project": line.project.number,
                "items": line.wished,
                "pieces": max(math.ceil(line.quantity), 1) * pieces,
            }
            for line in wishing
            if line.wished > max(math.ceil(line.quantity), 1) * pieces
        ]
        text = ", ".join(found[:limit])
        return f"{text} {_('and others')}" if len(found) > limit else text

    def _check_service_kept(self, errors: dict[str, Any]) -> None:
        """PRD-044: the service product of a job function stays a service as long as the function exists."""
        if self.pk is None or self.kind == ProductKind.SERVICE or "kind" in errors:
            return
        function = self.service_job_function
        if function is not None:
            errors["kind"] = _(
                "This product is the service product of the job function %(function)s and stays a service."
            ) % {"function": function.name}

    def _check_vehicle_kept(self, errors: dict[str, Any]) -> None:
        """LOG-001: a vehicle booked in projects stays a vehicle of its type – the bookings bill by its rates."""
        if self.pk is None or "kind" in errors or "vehicle_type" in errors:
            return
        stored = Product.objects.filter(pk=self.pk).values_list("kind", "vehicle_type").first()
        if stored is None or stored == (self.kind, self.vehicle_type):
            return
        if stored[0] != ProductKind.VEHICLE:
            # Material planned or packed as this product would drop out of availability and packing
            # lists unnoticed; "In den Fuhrpark übernehmen" on its model makes a vehicle product of its own (LOG-016).
            if self.kind == ProductKind.VEHICLE and (self.material_lines.exists() or self.used_in_kits.exists()):
                errors["kind"] = _(
                    "This product is planned as material or part of a kit and cannot become a vehicle. Take its "
                    "material model into the fleet instead (“Take into the fleet” on the model's page)."
                )
            return
        if self.vehicle_lines.exists():
            errors["kind" if self.kind != ProductKind.VEHICLE else "vehicle_type"] = _(
                "This vehicle is booked in projects. It stays a vehicle of its type."
            )

    @property
    def service_job_function(self) -> Any:
        """PRD-044: the job function this product is the service product of, or ``None``."""
        if self.pk is None:
            return None
        try:
            return self.job_function
        except models.ObjectDoesNotExist:
            return None

    def _check_prices(self, errors: dict[str, Any]) -> None:
        """PRD-013: a product needs its price – exactly one (PRD-047).

        A sale product has its sale price and no other price; every other
        product its price and never a sale price – what is sold is a sale
        product.

        PER-037: a service may be without price yet – the start data
        brings the job functions with their service products, and the price
        is entered later; until then their crew lines cost the customer 0.
        """
        if self.kind == ProductKind.SALE:
            if self.sale_price is None:
                errors["sale_price"] = _("A sale product needs a sale price.")
            if self.price is not None:
                errors["price"] = _("A sale product has only its sale price.")
        elif self.sale_price is not None:
            errors["sale_price"] = _("Only sale products have a sale price. To sell it, create a sale product.")
        if self.kind == ProductKind.VEHICLE:
            self._check_vehicle_rates(errors)
            return
        self._check_no_vehicle_rates(errors)
        if self.is_percent_surcharge:
            if self.surcharge_percent is None:
                errors["surcharge_percent"] = _("A percentage surcharge needs a percentage.")
            return
        if self.kind in (ProductKind.SERVICE, ProductKind.SALE):
            return
        if self.price is None:
            errors["price"] = _("Enter the price.")

    def _check_vehicle_rates(self, errors: dict[str, Any]) -> None:
        """LOG-005, LOG-006: a motor vehicle needs its price per kilometre, a trailer the price it is billed by.

        A motor vehicle is billed per kilometre only: it has no day price and
        no sale price. A trailer is billed per day (the day price, with the
        rental scale) or per kilometre, as preset for new bookings; the other
        rate may be given too, for bookings switched in the project. Only a
        motor vehicle carries the surcharge for trips with a trailer. A sale
        price it never has (see :meth:`_check_prices`).
        """
        if self.vehicle_type == VehicleType.CAR:
            if self.price_per_km is None:
                errors["price_per_km"] = _("A motor vehicle is billed per kilometre: enter the price per kilometre.")
            if self.price is not None:
                errors["price"] = _("A motor vehicle is billed per kilometre and has no price per day.")
            if self.cost_per_day is not None:
                errors["cost_per_day"] = _("Only a trailer has an internal cost per day.")
        elif self.vehicle_type == VehicleType.TRAILER:
            if self.trailer_billing == TrailerBilling.KM and self.price_per_km is None:
                errors["price_per_km"] = _("This trailer is billed per kilometre: enter the price per kilometre.")
            elif self.trailer_billing != TrailerBilling.KM and self.price is None:
                errors["price"] = _("This trailer is billed per day: enter the price per day.")
            if self.trailer_surcharge_per_km is not None:
                errors["trailer_surcharge_per_km"] = _("Only a motor vehicle carries a surcharge for trailers.")
        else:
            errors["vehicle_type"] = _("Choose whether this is a motor vehicle or a trailer.")

    def _check_no_vehicle_rates(self, errors: dict[str, Any]) -> None:
        """LOG-005: the rates of a vehicle belong to vehicles only."""
        if self.vehicle_type:
            errors["vehicle_type"] = _("Only a vehicle has a vehicle type.")
        for name in ("price_per_km", "trailer_surcharge_per_km", "cost_per_km", "cost_per_day"):
            if getattr(self, name) is not None:
                errors[name] = _("Only vehicles have rates per kilometre or internal costs per day.")

    @property
    def is_vehicle(self) -> bool:
        """LOG-002: a vehicle or trailer of the fleet, planned under "Logistik"."""
        return self.kind == ProductKind.VEHICLE

    @property
    def is_car(self) -> bool:
        """LOG-005: a motor vehicle – billed per kilometre, it can pull a trailer."""
        return self.kind == ProductKind.VEHICLE and self.vehicle_type == VehicleType.CAR

    @property
    def is_trailer(self) -> bool:
        """LOG-005: a trailer – billed per day or per kilometre."""
        return self.kind == ProductKind.VEHICLE and self.vehicle_type == VehicleType.TRAILER

    # --- Derived properties -------------------------------------------------

    @property
    def tracks_stock(self) -> bool:
        """Whether availability is checked for this product (PRD-030).

        True for rental and sale products in categories with own stock. Kits
        are not counted here: their availability follows from their
        components (VFG-008).
        """
        return self.kind in STOCK_KINDS and self.category.tracks_stock

    @property
    def is_kit(self) -> bool:
        """Whether the product consists of other products (PRD-022)."""
        return self.kind == ProductKind.KIT

    @property
    def is_percent_surcharge(self) -> bool:
        """Whether this is a surcharge calculated as a percentage (PRD-031)."""
        return self.kind == ProductKind.SURCHARGE and self.surcharge_type == SurchargeType.PERCENT

    @property
    def uses_rental_days(self) -> bool:
        """Whether rental days and scale apply, i.e. the product is billed per day."""
        return self.billing_mode in BillingMode.daily_modes() and self.price is not None

    def effective_rental_scale(self) -> RentalScale | None:
        """Return the rental scale that applies to this product (PRD-036).

        The most specific setting wins: the product itself, then its category
        (walking up to the main category), then the system default. Products
        that are not billed per day and products set to "no scale" have none.
        """
        if not self.uses_rental_days or self.rental_scale_mode == ScaleMode.NONE:
            return None
        if self.rental_scale_mode == ScaleMode.CUSTOM and self.rental_scale is not None:
            return self.rental_scale
        for category in reversed(self.category.ancestors_and_self()):
            if category.rental_scale is not None:
                return category.rental_scale
        return RentalScale.get_default()

    def is_used_in_projects(self) -> bool:
        """Whether any project line refers to this product (PRD-011) – a material line, or a vehicle booking (LOG-001)."""
        return self.material_lines.exists() or self.vehicle_lines.exists()


class KitComponent(AuditedModel):
    """One ingredient of a kit: a product and how many of it (PRD-022).

    Example: kit ``T-100 Aktivbox-Set`` has three components, each with
    quantity 1: ``T-010`` speaker, ``S-020`` stand, ``K-010`` cable. The
    components stay rentable on their own (PRD-004).
    """

    kit = models.ForeignKey(Product, verbose_name=_("kit"), on_delete=models.CASCADE, related_name="components")
    component = models.ForeignKey(
        Product, verbose_name=_("component"), on_delete=models.PROTECT, related_name="used_in_kits"
    )
    quantity = models.PositiveIntegerField(_("quantity"), default=1, validators=[MinValueValidator(1)])
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("kit component")
        verbose_name_plural = _("kit components")
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["kit", "component"], name="kit_component_unique")]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.component.article_number}"

    def audit_parent(self) -> models.Model | None:
        """Show component changes in the history of the kit."""
        return self.kit

    def clean(self) -> None:
        """A kit must not contain itself, directly or through other kits."""
        super().clean()
        if self.kit_id is None or self.component_id is None:
            return
        if self.kit.kind != ProductKind.KIT:
            raise ValidationError(_("Only products of the kind “kit” can have components."))
        if self.component.kind in {ProductKind.SURCHARGE, ProductKind.SUBRENTAL}:
            raise ValidationError({"component": _("Surcharges and subrentals cannot be part of a kit.")})
        if self.component.kind in LOGISTICS_KINDS:
            # LOG-001: vehicles are planned under "Logistik", never as part of the material.
            raise ValidationError({"component": _("Vehicles are planned under Logistics, not in a kit.")})
        if self.component.kind in CREW_ONLY_KINDS:
            # PRD-044: a service is planned with its job function in the crew planning, not with material.
            raise ValidationError(
                {"component": _("Services are planned with their job function under Personnel, not in a kit.")}
            )
        # PRD-043: a kit of customer material holds only that customer's material, and customer material is never
        # part of a kit offered to others.
        if self.component.owner_id != self.kit.owner_id:
            if self.kit.owner_id is None:
                raise ValidationError({"component": _("Customer material cannot be part of a kit of your own.")})
            raise ValidationError(
                {"component": _("A kit of customer material holds only material of the same customer.")}
            )
        from rentalars.products.services import kit_contains

        if self.component_id == self.kit_id or kit_contains(self.component_id, self.kit_id):
            raise ValidationError({"component": _("A kit cannot contain itself.")})


class FixtureTypeMapping(models.Model):
    """Which product a fixture type of a lighting plot stands for (PRJ-077).

    A plot in the MVR format names each fixture by its GDTF file, e.g.
    ``Robe_Lighting@Robin_T1_Profile.gdtf``, and the DMX mode it runs in.
    When a plot is taken over into a project, the product chosen for each
    type is remembered here, so that the next plot with the same type gets
    the same product suggested at once.

    The keys are stored in a normalised form (lower case, without
    ``.gdtf``), see ``projects.mvr.spec_key`` and ``projects.mvr.mode_key``.
    An empty mode is allowed: the product then stands for every mode.
    """

    gdtf_spec = models.CharField(_("GDTF fixture type"), max_length=200)
    gdtf_mode = models.CharField(_("DMX mode"), max_length=200, blank=True)
    label = models.CharField(_("fixture type"), max_length=250, blank=True, help_text=_("Manufacturer and model."))
    product = models.ForeignKey(
        Product, verbose_name=_("product"), on_delete=models.CASCADE, related_name="fixture_type_mappings"
    )
    updated_at = models.DateTimeField(_("last used"), default=timezone.now)

    class Meta:
        verbose_name = _("fixture type mapping")
        verbose_name_plural = _("fixture type mappings")
        ordering = ["gdtf_spec", "gdtf_mode"]
        constraints = [models.UniqueConstraint(fields=["gdtf_spec", "gdtf_mode"], name="fixture_type_mapping_unique")]

    def __str__(self) -> str:
        return f"{self.label or self.gdtf_spec} → {self.product}"


# Accessory and replacement suggestions; PRD-023, VFG-015: accessories, replacements and dismissed suggestions – tables of this module, in a file of its own.
from rentalars.products.relation_models import DismissedSuggestion, ProductRelation, RelationKind  # noqa: E402, F401
