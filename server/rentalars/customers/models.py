# SPDX-License-Identifier: GPL-3.0-or-later
"""Customers and their contacts (chapter 5.4)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.uploads import validate_document_upload
from rentalars.customers.names import join_name, parse_name, tidy


class CustomerKind(models.TextChoices):
    """The two kinds of customer (KND-002)."""

    COMPANY = "company", _("company or organisation")
    PRIVATE = "private", _("private person")


#: A VAT identification number: two letters for the country, then 2 to 13 letters or digits
#: (DE123456789, ATU12345678, NL123456789B01).
VAT_ID_PATTERN = re.compile(r"^[A-Z]{2}[0-9A-Z+*]{2,13}$")


def validate_vat_id(value: str) -> None:
    """Check the form of a VAT identification number (KND-006); whether it exists is not checked."""
    if value and not VAT_ID_PATTERN.match(value):
        raise ValidationError(
            _("A VAT ID starts with the country code and has no spaces, e.g. DE123456789."), code="invalid"
        )


class Customer(AuditedModel):
    """A customer with billing address (KND-003) and commercial details (KND-006).

    The address on the customer is its main billing address. Further billing
    and delivery addresses are :class:`CustomerAddress` records (KND-005).

    Customers that have projects are never deleted (KND-010); the foreign key
    from ``Project`` is protected. For erasing personal data there is
    ``customers.services.anonymise_customer`` instead.
    """

    number = models.CharField(_("customer number"), max_length=30, unique=True, editable=False)
    kind = models.CharField(_("kind"), max_length=10, choices=CustomerKind.choices, default=CustomerKind.COMPANY)
    name = models.CharField(_("name or company"), max_length=200)
    name_addition = models.CharField(_("addition"), max_length=200, blank=True, help_text=_("Department, c/o …"))
    street = models.CharField(_("street and number"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    country = models.CharField(_("country"), max_length=80, blank=True)
    email = models.EmailField(_("e-mail"), blank=True)
    phone = models.CharField(_("phone"), max_length=60, blank=True)
    note = models.TextField(_("note"), blank=True)
    # --- Commercial details (KND-006) --------------------------------------
    vat_id = models.CharField(
        _("VAT ID"), max_length=30, blank=True, validators=[validate_vat_id], help_text=_("e.g. DE123456789")
    )
    # IMP-013: taken over from bookkeeping programs such as Lexware, next to the VAT ID.
    tax_number = models.CharField(_("tax number"), max_length=40, blank=True)
    # DOK-006: invoices to public authorities carry their routing ID (Leitweg-ID) as buyer reference.
    buyer_reference = models.CharField(
        _("Leitweg-ID or buyer reference"),
        max_length=100,
        blank=True,
        help_text=_(
            "For invoices to public authorities: the Leitweg-ID. Empty: the electronic invoice names the project "
            "number as buyer reference."
        ),
    )
    payment_terms_days = models.PositiveSmallIntegerField(
        _("payment terms in days"),
        null=True,
        blank=True,
        validators=[MaxValueValidator(365)],
        help_text=_("Empty: as in the company settings."),
    )
    default_discount_percent = models.DecimalField(
        _("standard discount in percent"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=_("Taken over by every new material line of the customer's projects; changeable per line."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    anonymised_at = models.DateTimeField(_("anonymised"), null=True, blank=True, editable=False)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    # DOK-011: the contact in Lexware Office that invoices of this customer are booked on – found by the
    # customer number or created there when the first invoice is handed over.
    lexware_contact_id = models.CharField(_("contact in Lexware Office"), max_length=40, blank=True, editable=False)

    #: The discount is a price detail (AUT-019): only people with the price right see it, here and in the log.
    audit_sensitive: ClassVar[dict[str, str]] = {"default_discount_percent": SpecialRight.PRICES}

    class Meta:
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def address_lines(self) -> list[str]:
        """The billing address as printable lines, without empty ones."""
        lines = [self.name, self.name_addition, self.street, f"{self.postal_code} {self.city}".strip(), self.country]
        return [line for line in lines if line]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Store the VAT ID in capitals and without spaces (KND-006)."""
        self.vat_id = "".join(self.vat_id.split()).upper()
        super().save(*args, **kwargs)

    def clean_fields(self, exclude: Any = None) -> None:
        """The VAT ID is checked in its stored form: "de 123 456 789" is DE123456789."""
        self.vat_id = "".join(self.vat_id.split()).upper()
        super().clean_fields(exclude=exclude)

    def default_address(self, kind: str) -> CustomerAddress | None:
        """The further address marked as default for billing or delivery, if any (KND-005)."""
        return self.addresses.filter(kind=kind, is_default=True).first()

    @property
    def is_anonymised(self) -> bool:
        """Whether the personal data of this customer was erased (KND-010)."""
        return self.anonymised_at is not None

    @property
    def primary_contact(self) -> Contact | None:
        """The main contact person, if one is marked (KND-004)."""
        return self.contacts.filter(is_primary=True).first()


class GreetingStyle(models.TextChoices):
    """How a mail to a contact begins (KND-004: greeting per contact)."""

    FORMAL = "formal", _("Formal (Dear Ms Berg)")
    PERSONAL = "personal", _("Personal with first name (Hello Anna)")
    CUSTOM = "custom", _("Own greeting")


class Contact(AuditedModel):
    """A contact person at a customer (KND-004).

    At most one contact per customer is the primary one; saving a contact as
    primary takes the mark away from the others.

    First and last name are stored apart. ``name`` stays the full
    display name ("Anna Berg") and is derived from them when the contact is
    saved, so that lists, search, exports and the API keep working with it; a
    contact saved with only a ``name`` gets its first and last name from
    :func:`~rentalars.customers.names.split_name`. The greeting of mails to
    the contact is set per contact (``greeting_style``, ``greeting_text``,
    see ``customers.greetings``).
    """

    customer = models.ForeignKey(
        Customer, verbose_name=_("customer"), on_delete=models.CASCADE, related_name="contacts"
    )
    # IMP-013: the salutation comes with contacts imported from Lexware and similar programs.
    salutation = models.CharField(_("salutation"), max_length=40, blank=True, help_text=_("e.g. Ms, Mr, Dr"))
    name = models.CharField(_("name"), max_length=200)
    first_name = models.CharField(_("first name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"), max_length=100, blank=True)
    position = models.CharField(
        pgettext_lazy("contact", "position"), max_length=120, blank=True, help_text=_("e.g. technical director")
    )
    email = models.EmailField(_("e-mail"), blank=True)
    phone = models.CharField(_("phone"), max_length=60, blank=True)
    is_primary = models.BooleanField(_("primary contact"), default=False)
    greeting_style = models.CharField(
        _("greeting in e-mails"), max_length=10, choices=GreetingStyle.choices, default=GreetingStyle.FORMAL
    )
    greeting_text = models.CharField(
        _("own greeting"), max_length=200, blank=True, help_text=_("e.g. “Dear Anna,” – used as typed.")
    )

    #: ``name`` is derived from first and last name; the history shows those two.
    audit_exclude: ClassVar[frozenset[str]] = frozenset({"name"})

    class Meta:
        verbose_name = _("contact")
        verbose_name_plural = _("contacts")
        ordering = ["-is_primary", "last_name", "first_name", "name"]

    def __str__(self) -> str:
        return self.name

    def audit_parent(self) -> models.Model | None:
        """Show contact changes in the history of the customer."""
        return self.customer

    def tidy_names(self) -> None:
        """Make ``name`` and the two parts agree: the parts win; a bare ``name`` is split (KND-004).

        From a bare name (:func:`~rentalars.customers.names.parse_name`) a leading "Frau"/"Herr" becomes the
        salutation when that is empty (else it is dropped) and a remark after a comma becomes the position when
        that is empty. ``name`` is always the parts joined; whether it fits is checked by :meth:`clean`.
        """
        self.first_name, self.last_name = tidy(self.first_name), tidy(self.last_name)
        if not (self.first_name or self.last_name):
            parsed = parse_name(self.name)
            self.first_name, self.last_name = parsed.first_name, parsed.last_name
            if parsed.salutation and not self.salutation:
                self.salutation = parsed.salutation[: self._meta.get_field("salutation").max_length]
            if parsed.remark and not self.position:
                self.position = parsed.remark[: self._meta.get_field("position").max_length]
        self.name = join_name(self.first_name, self.last_name)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and keep "primary contact" unique per customer."""
        self.tidy_names()
        # Validation (``clean``) refuses a full name over 200 characters; a contact saved without it is cut, not lost.
        self.name = self.name[: self._meta.get_field("name").max_length]
        if (
            not self.is_primary
            and not Contact.objects.filter(customer_id=self.customer_id).exclude(pk=self.pk).exists()
        ):
            # The first contact of a customer is the primary one automatically.
            self.is_primary = True
        super().save(*args, **kwargs)
        if self.is_primary:
            for other in Contact.objects.filter(customer_id=self.customer_id, is_primary=True).exclude(pk=self.pk):
                other.is_primary = False
                other.save()

    def clean_fields(self, exclude: Any = None) -> None:
        """A bare ``name`` (API, import, code) is split before the fields are checked; ``name`` is derived."""
        self.tidy_names()
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        """A last name is needed; contacts of an anonymised customer would bring personal data back."""
        super().clean()
        if not self.last_name:
            raise ValidationError({"last_name": _("A contact needs a last name.")})
        if self.greeting_style == GreetingStyle.CUSTOM and not tidy(self.greeting_text):
            # The browser, the API and the import all stop here: an own greeting that is not typed would be ignored.
            raise ValidationError({"greeting_text": _("Type the greeting to use, e.g. “Dear Anna,”.")})
        if len(self.name) > self._meta.get_field("name").max_length:
            # Both parts may have 100 characters; with the space between them the full name can be one too long.
            raise ValidationError(
                {"last_name": _("First and last name together are too long (at most 200 characters).")}
            )
        if self.customer_id is not None and self.customer.is_anonymised:
            raise ValidationError(_("This customer was anonymised and cannot get new contacts."))


class AddressKind(models.TextChoices):
    """What a further address of a customer is for (KND-005)."""

    BILLING = "billing", _("billing address")
    DELIVERY = "delivery", _("delivery address")


class CustomerAddress(AuditedModel):
    """A further address of a customer: another billing address or a delivery address (KND-005).

    The address on the customer itself remains its main billing address.
    A project can name one of these instead – a billing address for the
    invoice, a delivery address for the delivery note (DOK-003). One address
    per kind can be the default; new projects then take it.
    """

    customer = models.ForeignKey(
        Customer, verbose_name=_("customer"), on_delete=models.CASCADE, related_name="addresses"
    )
    kind = models.CharField(_("kind"), max_length=10, choices=AddressKind.choices, default=AddressKind.DELIVERY)
    label = models.CharField(_("label"), max_length=120, blank=True, help_text=_("e.g. “Warehouse Nord”"))
    name = models.CharField(
        _("name or company"), max_length=200, blank=True, help_text=_("Empty: the name of the customer.")
    )
    name_addition = models.CharField(_("addition"), max_length=200, blank=True, help_text=_("Department, c/o …"))
    street = models.CharField(_("street and number"), max_length=200)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=120)
    country = models.CharField(_("country"), max_length=80, blank=True)
    is_default = models.BooleanField(_("default"), default=False, help_text=_("New projects take this address."))

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["kind", "-is_default", "label", "city"]

    def __str__(self) -> str:
        place = ", ".join(part for part in (self.street, self.city) if part)
        return f"{self.label}: {place}" if self.label else place

    def audit_parent(self) -> models.Model | None:
        """Show address changes in the history of the customer."""
        return self.customer

    @property
    def address_lines(self) -> list[str]:
        """The address as printable lines, without empty ones."""
        lines = [
            self.name or self.customer.name,
            self.name_addition,
            self.street,
            f"{self.postal_code} {self.city}".strip(),
            self.country,
        ]
        return [line for line in lines if line]

    def clean(self) -> None:
        """No new addresses for an anonymised customer."""
        super().clean()
        if self.customer_id is not None and self.customer.is_anonymised:
            raise ValidationError(_("This customer was anonymised and cannot get new addresses."))

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save and keep "default" unique per customer and kind."""
        super().save(*args, **kwargs)
        if self.is_default:
            for other in CustomerAddress.objects.filter(
                customer_id=self.customer_id, kind=self.kind, is_default=True
            ).exclude(pk=self.pk):
                other.is_default = False
                other.save()


class Venue(AuditedModel):
    """A place where events take place, as master data of its own (KND-009).

    Projects and their phases can name a venue (PRJ-006); its address, the
    contact on site and the notes for loading, power and the hall then show
    with the project and in the deployment view of the crew.
    """

    name = models.CharField(_("name"), max_length=200)
    street = models.CharField(_("street and number"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    country = models.CharField(_("country"), max_length=80, blank=True)
    contact_name = models.CharField(_("contact on site"), max_length=200, blank=True)
    contact_phone = models.CharField(_("phone on site"), max_length=60, blank=True)
    contact_email = models.EmailField(_("e-mail on site"), blank=True)
    access_notes = models.TextField(
        _("access and loading"), blank=True, help_text=_("Loading bay, height limits, parking, keys …")
    )
    power_notes = models.TextField(_("power"), blank=True, help_text=_("Connections, fuses, distances …"))
    notes = models.TextField(_("notes"), blank=True)
    hall_plan = models.FileField(
        _("hall plan"),
        upload_to="venues/",
        blank=True,
        validators=[validate_document_upload],
        help_text=_("PDF or image."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("venue")
        verbose_name_plural = _("venues")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name}, {self.city}" if self.city else self.name

    @property
    def address_lines(self) -> list[str]:
        """The address as printable lines, without empty ones."""
        lines = [self.street, f"{self.postal_code} {self.city}".strip(), self.country]
        return [line for line in lines if line]

    @property
    def address_one_line(self) -> str:
        """The address in one line, e.g. for a map search."""
        return ", ".join(self.address_lines)
