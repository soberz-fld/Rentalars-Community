# SPDX-License-Identifier: GPL-3.0-or-later
"""Master data shared by several modules (ADM-002).

Categories are used by material *and* products (PRD-009). Units, tax rates,
manufacturers, suppliers and storage locations are simple reference lists.
Master data that is in use cannot be deleted, only deactivated (ADM-006); the
database enforces this through protected foreign keys.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel
from rentalars.core.money import decimal_separator

#: A category code consists of capital letters only (PRD-029).
CATEGORY_CODE_PATTERN = re.compile(r"^[A-Z]+$")


class Unit(AuditedModel):
    """A unit of measure for products: piece, metre, day, hour … (PRD-012)."""

    name = models.CharField(_("name"), max_length=40, unique=True)
    abbreviation = models.CharField(_("abbreviation"), max_length=12)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("unit")
        verbose_name_plural = _("units")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TaxRate(AuditedModel):
    """A tax rate with the date from which it applies (PRD-016).

    A changed rate is entered as a new row with a new start date. Existing
    rows keep their percentage so that old projects still show the tax they
    were calculated with.
    """

    name = models.CharField(_("name"), max_length=60, unique=True)
    rate = models.DecimalField(
        _("rate in percent"),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    valid_from = models.DateField(_("valid from"), default=datetime.date(2007, 1, 1))
    is_default = models.BooleanField(_("default for new products"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("tax rate")
        verbose_name_plural = _("tax rates")
        ordering = ["-is_default", "name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Keep the percentage of a tax rate that documents already rely on."""
        super().clean()
        if self.pk is None:
            return
        stored = TaxRate.objects.filter(pk=self.pk).values_list("rate", flat=True).first()
        if stored is not None and stored != self.rate and self._is_in_use():
            raise ValidationError(
                {"rate": _("This tax rate is in use. Create a new tax rate instead of changing the percentage.")}
            )

    def _is_in_use(self) -> bool:
        """Whether any product or project line refers to this tax rate."""
        return any(
            getattr(self, relation.get_accessor_name()).exists()
            for relation in self._meta.related_objects
            if relation.one_to_many
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and make sure only one tax rate is the default."""
        super().save(*args, **kwargs)
        if self.is_default:
            for other in TaxRate.objects.filter(is_default=True).exclude(pk=self.pk):
                other.is_default = False
                other.save()

    @classmethod
    def get_default(cls) -> TaxRate | None:
        """Return the tax rate preselected for new products."""
        return cls.objects.filter(is_default=True, is_active=True).first() or cls.objects.filter(is_active=True).first()


class TaxAccount(AuditedModel):
    """A tax account (Steuerkonto): the account of the chart of accounts an incoming document is booked to.

    The positions of an incoming document (its *Kontierungen*) name the account their net amount belongs to – the
    tax adviser's chart of accounts, SKR 03 by default. The list is a proposal that the company checks and changes
    with its tax adviser: number, name and whether it is offered. An account a document refers to cannot be deleted,
    only deactivated.
    """

    number = models.CharField(
        _("account number"),
        max_length=10,
        unique=True,
        error_messages={"unique": _("An account with this number exists already.")},
        help_text=_("As in the chart of accounts of the tax adviser, e.g. 3400."),
    )
    name = models.CharField(_("name"), max_length=120)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("tax account")
        verbose_name_plural = _("tax accounts")
        ordering = ["number"]

    def __str__(self) -> str:
        return f"{self.number} {self.name}"

    def clean(self) -> None:
        """The number is digits only (the charts of accounts in use here have four to eight)."""
        super().clean()
        self.number = (self.number or "").strip()
        if self.number and not re.fullmatch(r"\d{3,10}", self.number):
            raise ValidationError({"number": _("Enter the account number in digits only, e.g. 3400.")})


class Manufacturer(AuditedModel):
    """A manufacturer of material (MAT-015)."""

    name = models.CharField(_("name"), max_length=120, unique=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("manufacturer")
        verbose_name_plural = _("manufacturers")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TaxOfficeKind(models.TextChoices):
    """What payments to a supplier that is the tax office are (DOK-052)."""

    NONE = "", _("not a tax office")
    VAT = "vat", _("tax office – turnover tax")
    INCOME = "income", _("tax office – income tax and other private taxes")


class Supplier(AuditedModel):
    """A dealer material was bought from, or a supplier of subrentals (MAT-019, PRJ-018).

    PRJ-106: e-mail address, phone and contact person of their own, for the
    correspondence of a subrental.
    """

    name = models.CharField(_("name"), max_length=120, unique=True)
    contact = models.CharField(_("contact"), max_length=250, blank=True, help_text=_("Who to ask there."))
    email = models.EmailField(
        _("e-mail"), blank=True, help_text=_("Mails of a project from and to this address belong to its subrentals.")
    )
    phone = models.CharField(_("phone"), max_length=60, blank=True)
    customer_number = models.CharField(_("our customer number there"), max_length=60, blank=True)
    # UIX-033, PRJ-097: where the supplier is – for the route link and the pickups of subrentals.
    street = models.CharField(_("street and number"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    country = models.CharField(_("country"), max_length=80, blank=True)
    note = models.TextField(_("note"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    #: DOK-052: payments to the tax office are no expenses of the EÜR; they are shown apart.
    tax_office = models.CharField(
        _("tax office"),
        max_length=6,
        blank=True,
        choices=TaxOfficeKind.choices,
        default=TaxOfficeKind.NONE,
        help_text=_(
            "Mark the tax office: what is paid to it is not an expense of the EÜR. Turnover tax is set against the "
            "balance of the turnover tax; income tax and the like are shown apart. Trade tax is an expense – leave this empty."
        ),
    )

    class Meta:
        verbose_name = _("supplier")
        verbose_name_plural = _("suppliers")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def address_lines(self) -> list[str]:
        """The address as printable lines, without empty ones (UIX-033)."""
        lines = [self.street, f"{self.postal_code} {self.city}".strip(), self.country]
        return [line for line in lines if line]

    @property
    def address_one_line(self) -> str:
        """The address in one line, as a route planner takes it; empty without street and city."""
        return ", ".join(self.address_lines)


class DocumentType(AuditedModel):
    """A kind of project document: stage plan, rider, contract, order … (PRJ-007, EML-021).

    ``visible_to_crew`` is the default for new files of this kind: a stage
    plan is for the crew, a contract is not. It can be changed per file.

    PRJ-089: files of a kind marked ``is_showfile`` are show files of
    a lighting console, media server or sound system; they note the console
    or software, its version and which one is current. The start data have
    the kind "Showfile" (created by the migrations of ``masterdata``).
    """

    name = models.CharField(_("name"), max_length=80, unique=True)
    visible_to_crew = models.BooleanField(
        _("visible to the crew"),
        default=False,
        help_text=_("Files of this kind are shown in the deployment view, too."),
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    is_showfile = models.BooleanField(
        _("show files"),
        default=False,
        help_text=_("Files of this kind note the console or software, its version and which one is current."),
    )

    class Meta:
        verbose_name = _("document type")
        verbose_name_plural = _("document types")
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


class StorageLocation(AuditedModel):
    """A place in the warehouse: hall, shelf, compartment, case (MAT-018).

    MAT-052: at most one location is the default – the "Hauptlager" of the
    start data, or the one chosen in the settings. The form "Neue Exemplare"
    preselects it.
    """

    name = models.CharField(_("name"), max_length=120)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("part of"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_default = models.BooleanField(
        _("default for new items"),
        default=False,
        help_text=_("The form for new items preselects this location. Only one location can be the default."),
    )

    class Meta:
        verbose_name = _("storage location")
        verbose_name_plural = _("storage locations")
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["parent", "name"], name="storage_location_unique_name")]

    def __str__(self) -> str:
        return self.path

    @property
    def path(self) -> str:
        """The full name including all parents, e.g. ``Halle 1 > Regal A > Fach 3``.

        Set from one query for all locations by :func:`remember_location_paths`
        when a page shows many; otherwise each parent is asked for.
        """
        known = self.__dict__.get("_known_path")
        if known is not None:
            return known
        names = [self.name]
        seen = {self.pk}
        current = self.parent
        while current is not None and current.pk not in seen:
            names.append(current.name)
            seen.add(current.pk)
            current = current.parent
        return " > ".join(reversed(names))

    def clean(self) -> None:
        """A location cannot be inside itself; a deactivated one is not the default (MAT-052)."""
        super().clean()
        current = self.parent
        seen: set[Any] = set()
        while current is not None and current.pk not in seen:
            if self.pk is not None and current.pk == self.pk:
                raise ValidationError({"parent": _("A storage location cannot be part of itself.")})
            seen.add(current.pk)
            current = current.parent
        if self.is_default and not self.is_active:
            raise ValidationError({"is_default": _("A deactivated storage location cannot be the default.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and make sure only one location is the default (MAT-052)."""
        super().save(*args, **kwargs)
        if self.is_default:
            for other in StorageLocation.objects.filter(is_default=True).exclude(pk=self.pk):
                other.is_default = False
                other.save()

    @classmethod
    def get_default(cls) -> StorageLocation | None:
        """The location new items get unless somebody chooses another one (MAT-052)."""
        return cls.objects.filter(is_default=True, is_active=True).first()


def location_paths() -> dict[int, str]:
    """Every storage location as its full path, e.g. ``Halle 1 > Regal A`` – from one query (MAT-018).

    A list of items shows the place of each; asking the database for the
    parents of every one would cost a query per row and level (NFA-012).
    """
    rows = {
        pk: (name, parent)
        for pk, name, parent in StorageLocation.objects.order_by().values_list("pk", "name", "parent_id")
    }
    paths: dict[int, str] = {}
    for pk in rows:
        names: list[str] = []
        seen: set[int] = set()
        current: int | None = pk
        while current is not None and current not in seen and current in rows:
            seen.add(current)
            name, current = rows[current]
            names.append(name)
        paths[pk] = " > ".join(reversed(names))
    return paths


def remember_location_paths(locations: Iterable[StorageLocation | None]) -> list[StorageLocation]:
    """Give these locations their path from one query, so that showing them asks nothing more.

    Returns:
        The locations (without ``None``), sorted by their path.
    """
    present = [location for location in locations if location is not None]
    if present:
        paths = location_paths()
        for location in present:
            location.__dict__["_known_path"] = paths.get(location.pk, location.name)
    return sorted(present, key=lambda location: location.path.casefold())


class CategoryManager(models.Manager["Category"]):
    """Queries that need the whole category tree."""

    def descendant_ids(self, category_id: int) -> set[int]:
        """Return the IDs of a category and all categories below it.

        The category table is small (some dozen rows), so the whole tree is
        loaded once and walked in memory instead of running a recursive query.
        """
        children: dict[int | None, list[int]] = {}
        for pk, parent_id in self.values_list("pk", "parent_id"):
            children.setdefault(parent_id, []).append(pk)
        result: set[int] = set()
        pending = [category_id]
        while pending:
            current = pending.pop()
            if current in result:
                continue
            result.add(current)
            pending.extend(children.get(current, []))
        return result

    def main_categories(self) -> models.QuerySet[Category]:
        """Return the top-level categories; only these carry a code."""
        return self.filter(parent__isnull=True)

    def in_tree_order(self, *, only_active: bool = False) -> list[Category]:
        """Return all categories the way a person reads a tree: each one below its parent.

        A selection list shows a category with its full path ("Ton >
        Mikrofone"). Sorted by the plain name, "Mikrofone" would stand
        between "Licht" and "Rigging", far from "Ton". Here the list is
        sorted by the path, so a category is followed by its subcategories.

        The whole table is loaded with one query and the categories are
        linked to each other in memory; asking each of them for its path then
        needs no further query.

        Args:
            only_active: Leave out deactivated categories.
        """
        categories = list(self.all())
        by_id = {category.pk: category for category in categories}
        for category in categories:
            if category.parent_id in by_id:
                category.parent = by_id[category.parent_id]
        categories.sort(key=lambda category: [part.name.lower() for part in category.ancestors_and_self()])
        return [category for category in categories if category.is_active or not only_active]

    def choices(self, *, empty_label: Any = "") -> list[tuple[Any, str]]:
        """Return the active categories as choices for a selection field, in tree order.

        ``empty_label``: the text of the empty entry; ``None`` for no entry; not given: "– please choose –".
        """
        if empty_label == "":
            empty_label = _("– please choose –")
        choices: list[tuple[Any, str]] = [
            (category.pk, category.path) for category in self.in_tree_order(only_active=True)
        ]
        return [("", empty_label), *choices] if empty_label is not None else choices


class FieldType(models.TextChoices):
    """Data types for category-specific fields (MAT-010)."""

    TEXT = "text", _("text")
    NUMBER = "number", _("number with unit")
    CHOICE = "choice", _("choice")
    BOOLEAN = "boolean", _("yes/no")


class ProductKindDefault(models.TextChoices):
    """Product kinds a category can preselect; mirrors ``products.ProductKind``."""

    RENTAL = "rental", _("rental product")
    SALE = "sale", _("sale or consumable")
    SERVICE = "service", _("service")
    KIT = "kit", _("kit")
    SURCHARGE = "surcharge", _("surcharge")
    SUBRENTAL = "subrental", _("subrental")
    INCIDENTAL = "incidental", _("incidental costs")  # PRD-045
    VEHICLE = "vehicle", _("vehicle")  # LOG-002


class Category(AuditedModel):
    """The common classification of material and products (MAT-007, PRD-009).

    Categories form a tree (MAT-008). Only **main categories** (those without
    a parent) have a ``code``; it is the letter part of article numbers such
    as ``K-005`` (PRD-007). Subcategories use the code of their main category.

    Rules enforced here:

    * Codes are unique and consist of capital letters (PRD-029).
    * A code cannot be changed once article numbers with it exist (PRD-029).
    * ``has_own_stock`` is false for categories whose products are never
      checked for availability: subrental, surcharges, services, transport
      (PRD-027, PRD-030).
    """

    name = models.CharField(_("name"), max_length=120)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("parent category"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    code = models.CharField(
        _("code"),
        max_length=6,
        blank=True,
        help_text=_("Capital letters; forms the first part of article numbers. Only for main categories."),
    )
    has_own_stock = models.BooleanField(
        _("own stock"),
        default=True,
        help_text=_("Products of categories without own stock are not checked for availability."),
    )
    # PRD-043: material that belongs to a customer and is stored here, e.g. the gear of a band ("Fremdmaterial").
    is_customer_material = models.BooleanField(
        _("customer material"),
        default=False,
        help_text=_(
            "Products of this category belong to a customer: they have an owner and no price, and they can only "
            "be planned in that customer's projects. Only for main categories with own stock."
        ),
    )
    is_active = models.BooleanField(_("active"), default=True)

    # VFG-005: buffer times that differ from the system-wide default.
    buffer_before_hours = models.DecimalField(
        _("buffer before use (hours)"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Empty: use the default."),
    )
    buffer_after_hours = models.DecimalField(
        _("buffer after use (hours)"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Empty: use the default."),
    )

    # PRD-030: presets for new products of this category.
    default_product_kind = models.CharField(
        _("preset: product kind"),
        max_length=12,
        choices=ProductKindDefault.choices,
        default=ProductKindDefault.RENTAL,
    )
    default_unit = models.ForeignKey(
        Unit,
        verbose_name=_("preset: unit"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    default_tax_rate = models.ForeignKey(
        TaxRate,
        verbose_name=_("preset: tax rate"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    default_billing_mode = models.CharField(
        _("preset: billing mode"),
        max_length=20,
        blank=True,
        help_text=_("Empty: follow the product kind."),
    )
    # PRD-034: a rental scale that differs from the system default.
    rental_scale = models.ForeignKey(
        "RentalScale",
        verbose_name=_("rental scale"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="categories",
        help_text=_("Empty: use the default scale."),
    )

    objects = CategoryManager()

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["parent", "name"], name="category_unique_name")]

    def __str__(self) -> str:
        return self.path

    @property
    def path(self) -> str:
        """The full name including all parents, e.g. ``Ton > Mikrofone``."""
        names = [category.name for category in self.ancestors_and_self()]
        return " > ".join(names)

    def ancestors_and_self(self) -> list[Category]:
        """Return the chain from the main category down to this category."""
        chain = [self]
        seen = {self.pk}
        current = self.parent
        while current is not None and current.pk not in seen:
            chain.append(current)
            seen.add(current.pk)
            current = current.parent
        chain.reverse()
        return chain

    @property
    def main_category(self) -> Category:
        """The top-level category this category belongs to (itself if it is one)."""
        return self.ancestors_and_self()[0]

    @property
    def effective_code(self) -> str:
        """The code of the main category; subcategories inherit it (PRD-009)."""
        return self.main_category.code

    @property
    def tracks_stock(self) -> bool:
        """Whether products of this category have stock of their own (PRD-027)."""
        return self.main_category.has_own_stock

    @property
    def holds_customer_material(self) -> bool:
        """PRD-043: whether products of this category belong to a customer; subcategories follow their main one."""
        return self.main_category.is_customer_material

    def clean(self) -> None:
        """Validate code rules and the tree structure."""
        super().clean()
        self.code = (self.code or "").strip().upper()
        self._check_not_own_ancestor()
        self._check_customer_material()

        if self.parent_id is not None:
            if self.code:
                raise ValidationError(
                    {"code": _("Only main categories have a code. Subcategories use it automatically.")}
                )
            return

        if not self.code:
            raise ValidationError({"code": _("A main category needs a code.")})
        if not CATEGORY_CODE_PATTERN.match(self.code):
            raise ValidationError({"code": _("The code may only consist of the capital letters A to Z.")})
        duplicate = Category.objects.filter(parent__isnull=True, code=self.code).exclude(pk=self.pk)
        if duplicate.exists():
            raise ValidationError({"code": _("This code is already used by another category.")})
        self._check_code_not_changed_while_in_use()

    def _check_not_own_ancestor(self) -> None:
        """A category cannot be placed below itself."""
        if self.pk is None or self.parent is None:
            return
        if self.pk in {category.pk for category in self.parent.ancestors_and_self()}:
            raise ValidationError({"parent": _("A category cannot be placed below itself.")})

    def _check_customer_material(self) -> None:
        """PRD-043: the mark "customer material" sits on a main category with own stock and is fixed once used.

        Customer material is counted like own material, so its category needs
        a stock. Products of the category either all have an owner or none
        has one; while there are products, the mark therefore stays as it is.
        """
        if not self.is_customer_material:
            stored = Category.objects.filter(pk=self.pk).values_list("is_customer_material", flat=True).first()
            if stored and self._has_products():
                raise ValidationError(
                    {
                        "is_customer_material": _(
                            "This category holds customer material. Move or delete its products first."
                        )
                    }
                )
            return
        if self.parent_id is not None:
            raise ValidationError(
                {"is_customer_material": _("Only main categories are marked; subcategories follow them.")}
            )
        if not self.has_own_stock:
            raise ValidationError(
                {"is_customer_material": _("Customer material is counted like own material: tick “own stock”.")}
            )
        stored = Category.objects.filter(pk=self.pk).values_list("is_customer_material", flat=True).first()
        if self.pk is not None and not stored and self._has_products():
            raise ValidationError(
                {"is_customer_material": _("This category has products of your own. Use a new category instead.")}
            )

    def _has_products(self) -> bool:
        """Whether any product belongs to this category or one below it."""
        if self.pk is None:
            return False
        from rentalars.products.models import Product

        return Product.objects.filter(category_id__in=Category.objects.descendant_ids(self.pk)).exists()

    def _check_code_not_changed_while_in_use(self) -> None:
        """PRD-029: a code with existing article numbers is frozen."""
        if self.pk is None:
            return
        stored_code = Category.objects.filter(pk=self.pk).values_list("code", flat=True).first()
        if stored_code and stored_code != self.code and self.has_article_numbers(stored_code):
            raise ValidationError(
                {
                    "code": _("Article numbers with the code %(code)s exist. The code can no longer be changed.")
                    % {"code": stored_code}
                }
            )

    @staticmethod
    def has_article_numbers(code: str) -> bool:
        """Whether any product carries an article number starting with ``code-``."""
        from rentalars.products.models import Product

        return Product.objects.filter(article_number__startswith=f"{code}-").exists()

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """PRD-029: a category whose code is in use can only be deactivated."""
        if self.parent_id is None and self.code and self.has_article_numbers(self.code):
            raise ValidationError(
                _("Article numbers with the code %(code)s exist. Deactivate the category instead of deleting it.")
                % {"code": self.code}
            )
        return super().delete(*args, **kwargs)

    def applicable_fields(self) -> list[CategoryField]:
        """Return the category-specific fields that apply to this category.

        A category uses its own fields. If it has none, it inherits those of
        the nearest parent that defines some. The first field in the list is
        "the" category-specific value of MAT-009.
        """
        for category in reversed(self.ancestors_and_self()):
            fields = list(category.fields.all())
            if fields:
                return fields
        return []

    @property
    def primary_field(self) -> CategoryField | None:
        """The field that holds the category-specific value of MAT-009, if defined."""
        fields = self.applicable_fields()
        return fields[0] if fields else None


#: MAT-049: labels of a category field that holds the power – a field of every material model
#: (``MaterialModel.power_w``).
POWER_FIELD_LABELS = frozenset({"leistung", "power"})
POWER_FIELD_UNITS = frozenset({"w", "watt"})


def is_power_field(label: str, unit: str, field_type: str) -> bool:
    """Whether a category field holds the power in watts (MAT-049), e.g. "Leistung" in W of the category Licht."""
    return (
        field_type == FieldType.NUMBER
        and (label or "").strip().lower() in POWER_FIELD_LABELS
        and (unit or "").strip().lower() in POWER_FIELD_UNITS
    )


class CategoryField(AuditedModel):
    """A category-specific field such as "length" for cables (MAT-009, MAT-010).

    The field with the lowest position is the one category-specific value
    required by MAT-009; the column "Kategoriespezifische Angabe" of the
    lists shows it. Further fields (MAT-010) appear in the form and on the
    page of the material model.
    """

    category = models.ForeignKey(Category, verbose_name=_("category"), on_delete=models.CASCADE, related_name="fields")
    label = models.CharField(_("label"), max_length=80)
    field_type = models.CharField(_("type"), max_length=10, choices=FieldType.choices, default=FieldType.TEXT)
    unit = models.CharField(_("unit"), max_length=20, blank=True, help_text=_("For numbers, e.g. m, W, kg."))
    choices = models.JSONField(_("options"), default=list, blank=True, help_text=_("For the type “choice”."))
    position = models.PositiveSmallIntegerField(_("position"), default=1)

    class Meta:
        verbose_name = _("category-specific field")
        verbose_name_plural = _("category-specific fields")
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.label}"

    def audit_parent(self) -> models.Model | None:
        """Show field changes in the history of the category."""
        return self.category

    def clean(self) -> None:
        """MAT-049: the power in watts is a field of every material model, not of a category."""
        super().clean()
        if is_power_field(self.label, self.unit, self.field_type):
            raise ValidationError(
                {"label": _("Every material model has a field “Power (W)” of its own. No category field is needed.")}
            )

    @property
    def label_with_unit(self) -> str:
        """The label with the unit in brackets, e.g. ``Länge (m)``."""
        return f"{self.label} ({self.unit})" if self.unit and self.field_type == FieldType.NUMBER else self.label

    def clean_value(self, raw_value: Any) -> str:
        """Check a value against the field type and return it as stored text.

        Raises:
            ValidationError: The value does not fit the type, e.g. text in a
                number field.
        """
        text = "" if raw_value is None else str(raw_value).strip()
        if not text:
            return ""
        if self.field_type == FieldType.NUMBER:
            number_text = text.replace(",", ".")
            if self.unit and number_text.lower().endswith(self.unit.lower()):
                number_text = number_text[: -len(self.unit)].strip()
            not_a_number = _("“%(value)s” is not a number for the field %(label)s.") % {
                "value": text,
                "label": self.label,
            }
            try:
                number = Decimal(number_text)
            except ArithmeticError as error:
                raise ValidationError(not_a_number) from error
            # Review (MAT-010, MAT-078): "NaN" and "Infinity" are no numbers – a stored "NaN" as the length
            # of a cable broke its inspection page; nor is "1e999999", which would be stored with all its digits.
            if not number.is_finite() or (number and not -15 <= number.adjusted() < 15):
                raise ValidationError(not_a_number)
            return format(number.normalize(), "f")
        if self.field_type == FieldType.CHOICE and self.choices and text not in self.choices:
            raise ValidationError(
                _("“%(value)s” is not one of the options of the field %(label)s.")
                % {"value": text, "label": self.label}
            )
        if self.field_type == FieldType.BOOLEAN:
            return "yes" if text.lower() in {"1", "true", "yes", "ja", "x"} else "no"
        return text

    def display_value(self, stored_value: str) -> str:
        """Format a stored value for people, e.g. ``5`` with unit ``m`` as ``5 m``."""
        if not stored_value:
            return ""
        if self.field_type == FieldType.NUMBER:
            number = stored_value.replace(".", decimal_separator())  # UIX-029
            return f"{number} {self.unit}".strip()
        if self.field_type == FieldType.BOOLEAN:
            return str(_("yes")) if stored_value == "yes" else str(_("no"))
        return stored_value


@dataclass(frozen=True)
class ScaleTable:
    """The content of one rental scale version, detached from the database.

    Price calculation loads the tables of all versions a project uses once
    and then asks them in memory, instead of querying per project line.
    """

    rows: list[tuple[int, Decimal]]
    extra_day_increment: Decimal = Decimal("0")

    def factor_for(self, days: int) -> Decimal:
        """Return the price factor for a number of rental days (PRD-015, PRD-038).

        Rules, in this order:

        1. A row for exactly this number of days: its factor.
        2. More days than the last row: the last factor plus
           ``extra_day_increment`` for every further day.
        3. A gap between rows: the factor of the next smaller row.
        4. Fewer days than the first row: the factor of the first row.

        Example with rows ``1 = 1.0``, ``2 = 1.5``, ``5 = 2.5`` and an
        increment of 0.25: 2 days give 1.5, 4 days give 1.5 (next smaller
        row), 7 days give 2.5 + 2 × 0.25 = 3.0.
        """
        if not self.rows:
            return Decimal("1")
        rows = sorted(self.rows)
        last_days, last_factor = rows[-1]
        if days > last_days:
            return last_factor + self.extra_day_increment * (days - last_days)
        factor = rows[0][1]
        for row_days, row_factor in rows:
            if row_days > days:
                break
            factor = row_factor
        return factor


class RentalScale(AuditedModel):
    """A table that turns a number of rental days into a price factor (PRD-015).

    Example: with the rows ``1 day = 1.0`` and ``2 days = 1.5`` a product with
    a daily price of 20.00 costs 20.00 for one day and 30.00 for two days.

    The rows are not stored on the scale itself but on a
    :class:`RentalScaleVersion`. Every edit creates a new version and leaves
    the old ones untouched. Project lines remember the version they were
    created with, which is how PRD-037 is met: a changed table affects new
    lines only, and existing lines keep calculating with the old state until
    someone switches the project over.

    Exactly one scale is the default for all products with daily rental
    (PRD-034); categories and products can point to a different one.
    """

    name = models.CharField(_("name"), max_length=80, unique=True)
    is_default = models.BooleanField(_("default scale"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("rental scale")
        verbose_name_plural = _("rental scales")
        ordering = ["-is_default", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and make sure only one scale is the default."""
        super().save(*args, **kwargs)
        if self.is_default:
            for other in RentalScale.objects.filter(is_default=True).exclude(pk=self.pk):
                other.is_default = False
                other.save()

    @classmethod
    def get_default(cls) -> RentalScale | None:
        """Return the scale used when neither product nor category name one."""
        return cls.objects.filter(is_default=True, is_active=True).first()

    @property
    def current_version(self) -> RentalScaleVersion | None:
        """The newest version; new project lines calculate with it."""
        return self.versions.order_by("-number").first()

    def factor_for(self, days: int) -> Decimal:
        """Return the factor of the current version for a number of rental days."""
        version = self.current_version
        return version.factor_for(days) if version else Decimal("1")

    @transaction.atomic
    def publish(
        self,
        rows: list[tuple[int, Decimal]],
        *,
        extra_day_increment: Decimal,
        created_by: Any = None,
    ) -> RentalScaleVersion:
        """Store a new state of the table as a new version (PRD-015, PRD-037).

        Args:
            rows: Pairs of ``(rental days, factor)``. Days must be unique and
                at least 1; factors must not be negative.
            extra_day_increment: What is added to the factor of the last row
                for every day beyond it (PRD-038).
            created_by: The user who edited the table.

        Returns:
            The new version. If nothing differs from the current version, the
            current version is returned and no new one is created.

        Raises:
            ValidationError: The rows are empty or contradict the rules above.
        """
        cleaned = sorted((int(days), Decimal(factor)) for days, factor in rows)
        if not cleaned:
            raise ValidationError(_("A rental scale needs at least one row."))
        if len({days for days, _factor in cleaned}) != len(cleaned):
            raise ValidationError(_("Every number of rental days may appear only once."))
        if any(days < 1 for days, _factor in cleaned):
            raise ValidationError(_("Rental days start at 1."))
        if any(factor < 0 for _days, factor in cleaned) or extra_day_increment < 0:
            raise ValidationError(_("Factors must not be negative."))

        current = self.current_version
        if (
            current is not None
            and current.extra_day_increment == extra_day_increment
            and [(row.days, row.factor) for row in current.rows.all()] == cleaned
        ):
            return current

        version = RentalScaleVersion.objects.create(
            scale=self,
            number=(current.number + 1) if current else 1,
            extra_day_increment=extra_day_increment,
            created_by=created_by,
        )
        RentalScaleRow.objects.bulk_create(
            RentalScaleRow(version=version, days=days, factor=factor) for days, factor in cleaned
        )
        from rentalars.core.audit import record_event

        record_event(
            self,
            "rental_scale.published",
            {
                "version": version.number,
                "rows": [[days, str(factor)] for days, factor in cleaned],
                "extra_day_increment": str(extra_day_increment),
            },
        )
        return version


class RentalScaleVersion(models.Model):
    """One immutable state of a rental scale table (PRD-037)."""

    scale = models.ForeignKey(RentalScale, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField(_("version"))
    extra_day_increment = models.DecimalField(
        _("increment per further day"),
        max_digits=7,
        decimal_places=3,
        default=Decimal("0"),
        help_text=_("Added to the last factor for every day beyond the last row."),
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("rental scale version")
        verbose_name_plural = _("rental scale versions")
        ordering = ["scale", "-number"]
        constraints = [models.UniqueConstraint(fields=["scale", "number"], name="rental_scale_version_unique")]

    def __str__(self) -> str:
        return f"{self.scale.name} v{self.number}"

    @property
    def is_current(self) -> bool:
        """Whether this is the newest version of its scale."""
        return not RentalScaleVersion.objects.filter(scale_id=self.scale_id, number__gt=self.number).exists()

    def as_table(self) -> ScaleTable:
        """Return the rows and the increment as plain values for calculations."""
        return ScaleTable(
            rows=[(row.days, row.factor) for row in self.rows.all()],
            extra_day_increment=self.extra_day_increment,
        )

    def factor_for(self, days: int) -> Decimal:
        """Return the price factor for a number of rental days; see :meth:`ScaleTable.factor_for`."""
        return self.as_table().factor_for(days)


class RentalScaleRow(models.Model):
    """One row of a rental scale version: rental days and their factor."""

    version = models.ForeignKey(RentalScaleVersion, on_delete=models.CASCADE, related_name="rows")
    days = models.PositiveSmallIntegerField(_("rental days"), validators=[MinValueValidator(1)])
    factor = models.DecimalField(
        _("factor"), max_digits=7, decimal_places=3, validators=[MinValueValidator(Decimal("0"))]
    )

    class Meta:
        verbose_name = _("rental scale row")
        verbose_name_plural = _("rental scale rows")
        ordering = ["days"]
        constraints = [models.UniqueConstraint(fields=["version", "days"], name="rental_scale_row_unique")]

    def __str__(self) -> str:
        return f"{self.days}: {self.factor}"
