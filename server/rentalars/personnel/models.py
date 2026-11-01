# SPDX-License-Identifier: GPL-3.0-or-later
"""People, job functions, hourly rates and absences (chapter 5.5).

Four tables:

``JobFunction``
    What somebody does on a job: sound engineer, stagehand, driver (PER-004).
    Each has exactly one service product, usually of category D, which
    carries the price charged to the customer (PER-008); the two
    belong together one to one (PRD-044): a new function brings its service
    product, a new service product its function.

``Person``
    Somebody who works on projects: employee, temporary staff or freelancer
    (PER-001, PER-002). Every person has exactly one user account and every
    account is a person (AUT-026): a new person gets an account
    – without a password until invited or given a one-time password –, and
    a new account gets its person. That is what lets everybody see "my
    deployments" and record "my times".

``PersonJobFunction``
    "Person A works as sound engineer for 35.00 an hour from 1 January on"
    (PER-005, PER-007). The rows are the assignment of functions to people
    *and* the history of their rates. Hourly rate, day rate and
    "valid from" are all optional (PER-029): "Person A works as sound
    engineer" is a row of its own.

``Absence``
    Holiday, sickness, not available – with a period (PER-011).

``QualificationType`` and ``Qualification``
    What a person has proven: driving licence classes, mobile elevating work
    platform, rigging, first aid – with the date it expires and a scan of
    the certificate (PER-014).

Two prices, never to be confused (PER-008): the **hourly rate** of a person
is what the work *costs* the company – and so is the **day rate** (PER-009,
PER-029). What the customer *pays* is the price of the service product of the
job function. Hourly and day rates need the special right "see hourly rates
and personnel costs" (AUT-019, PER-010).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.i18n import local_pattern
from rentalars.products.models import Product, ProductKind


class EmploymentKind(models.TextChoices):
    """How somebody works for the company (PER-002)."""

    EMPLOYEE = "employee", _("permanent employee")
    TEMPORARY = "temporary", _("temporary staff")
    FREELANCER = "freelancer", _("freelancer")


class JobFunction(AuditedModel):
    """A function people are planned in, e.g. "sound engineering" (PER-004).

    Called "job function" in the code: "function" would be confused with
    functions of the program, and "role" already names the roles of the
    rights system (catalogue 2.1).
    """

    name = models.CharField(
        _("name"),
        max_length=80,
        unique=True,
        error_messages={"unique": _("A job function with this name already exists.")},
    )
    # PRD-044: one service product per function and one function per service product. Created with the
    # function when it has none (``save``); its price, tax rate and hour tiers are kept on the product.
    service_product = models.OneToOneField(
        Product,
        verbose_name=_("service product"),
        on_delete=models.PROTECT,
        related_name="job_function",
        help_text=_("The product whose price the customer pays for this function, per hour."),
    )
    guide_cost_rate = models.DecimalField(
        _("guide value for internal costs per hour"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Used in the calculation while a crew line has no person yet."),
    )
    # PER-029: the same per day, for crew lines charged per day.
    guide_daily_cost_rate = models.DecimalField(
        _("guide value for internal costs per day"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Used for days while a crew line has no person yet, or the person has no day rate."),
    )
    # PER-035: the cost of an hour beyond the limit of hours per day of the service product.
    guide_cost_rate_above_limit = models.DecimalField(
        _("guide value per hour from the limit"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_(
            "Internal costs of an hour beyond the limit of hours per day of the service product, while a crew line "
            "has no person or the person has no own rate. Empty: the guide value per hour."
        ),
    )
    max_discount_percent = models.DecimalField(
        _("maximum discount in percent"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=_(
            "No crew line of this function is discounted more – by its own discount, its group's or the "
            "project's. 0: never discounted. Empty: no limit."
        ),
    )
    is_active = models.BooleanField(_("active"), default=True)

    audit_sensitive = {
        "guide_cost_rate": SpecialRight.PERSONNEL_COSTS,
        "guide_daily_cost_rate": SpecialRight.PERSONNEL_COSTS,
        "guide_cost_rate_above_limit": SpecialRight.PERSONNEL_COSTS,
    }

    class Meta:
        verbose_name = _("job function")
        verbose_name_plural = _("job functions")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """PER-008: the customer price comes from a *service* product."""
        super().clean()
        self.name = (self.name or "").strip()
        if self.service_product_id and self.service_product.kind != ProductKind.SERVICE:
            raise ValidationError(
                {"service_product": _("Choose a service product (category D), not a product with stock.")}
            )

    def clean_fields(self, exclude: Any = None) -> None:
        """A new function may come without service product: :meth:`save` creates it (PRD-044)."""
        exclude = set(exclude or ())
        if self.service_product_id is None:
            exclude.add("service_product")
        super().clean_fields(exclude=exclude)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """PRD-044: a function without service product gets one of the same name, before it is stored."""
        if self.service_product_id is None:
            from rentalars.personnel.services import create_service_product

            self.service_product = create_service_product(self.name)
        super().save(*args, **kwargs)


class Person(AuditedModel):
    """Somebody who works on projects (PER-001 to PER-003).

    Contact data and colleagues (PER-019)
        The name is visible to everybody who works on the same deployment.
        Phone and e-mail are visible to colleagues only if the person agreed:
        ``share_phone`` and ``share_email``, both off by default. Project
        management and personnel planning see them in any case.

    Privacy (NFA-009)
        A person with crew lines or time entries is never deleted; the data
        that identifies the person can be erased instead, see
        ``personnel.privacy.anonymise_person``.
    """

    first_name = models.CharField(_("first name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"), max_length=100)
    kind = models.CharField(_("kind"), max_length=12, choices=EmploymentKind.choices, default=EmploymentKind.EMPLOYEE)
    position = models.CharField(
        _("position in the company"),
        max_length=120,
        blank=True,
        help_text=_("For example “Head of lighting” – also for the e-mail signature."),
    )
    email = models.EmailField(_("e-mail"), blank=True)
    phone = models.CharField(_("phone"), max_length=60, blank=True)
    note = models.TextField(_("note"), blank=True)
    # ZEI-027: the way to work, deducted twice (there and back) from the trips of a day by kilometre.
    commute_km = models.DecimalField(
        _("distance home – company (km)"),
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("2000"))],
        help_text=_(
            "Twice this distance (there and back) is deducted once a day per project from trips by kilometre. "
            "Empty: nothing is deducted."
        ),
    )

    # --- Freelancers (PER-003) ----------------------------------------------
    company = models.CharField(_("company"), max_length=200, blank=True)
    street = models.CharField(_("street and number"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    tax_number = models.CharField(_("tax number"), max_length=40, blank=True)
    vat_id = models.CharField(_("VAT ID"), max_length=40, blank=True)

    # --- Account and visibility (AUT-012, AUT-026, PER-019) -----------------
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user account"),
        on_delete=models.PROTECT,
        related_name="person",
        editable=False,
        help_text=_("The account this person logs in with. Created with the person."),
    )
    share_phone = models.BooleanField(
        _("colleagues may see my phone number"),
        default=False,
        help_text=_("Colleagues on the same deployment. Project management and personnel planning always see it."),
    )
    share_email = models.BooleanField(_("colleagues may see my e-mail address"), default=False)
    # API-015 (mobile app): when each of the four contact fields last changed, on
    # whatever way – :meth:`save` notes it. A change the app made offline counts only if it is later
    # (``personnel.own_api``). Not in the change log: the log has the changes themselves.
    phone_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    email_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    share_phone_changed_at = models.DateTimeField(null=True, blank=True, editable=False)
    share_email_changed_at = models.DateTimeField(null=True, blank=True, editable=False)

    # --- Calendars (PER-022, PER-023; the linked calendars are ``CalendarFeed`` rows, PER-031) ------
    calendar_token = models.CharField(max_length=64, blank=True, editable=False, db_index=True)
    caldav_url = models.URLField(
        _("CalDAV calendar for my deployments"),
        max_length=500,
        blank=True,
        help_text=_(
            "The address of a calendar on a CalDAV server, e.g. Nextcloud, iCloud or mailbox.org. Rentalars "
            "writes the deployments into it, so that they reach phones even when Rentalars is not reachable "
            "from the internet."
        ),
    )
    caldav_username = models.CharField(_("CalDAV username"), max_length=200, blank=True)
    caldav_password_encrypted = models.TextField(blank=True, editable=False)
    caldav_synced_at = models.DateTimeField(_("calendar last written"), null=True, blank=True, editable=False)
    caldav_error = models.CharField(_("problem with the CalDAV calendar"), max_length=250, blank=True, editable=False)
    # How the exchange with the calendars goes; written with ``update()`` by ``personnel.calendars`` only.
    caldav_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    caldav_failures = models.PositiveSmallIntegerField(default=0, editable=False)
    caldav_dirty = models.BooleanField(default=False, editable=False)

    is_active = models.BooleanField(_("active"), default=True)
    anonymised_at = models.DateTimeField(_("anonymised"), null=True, blank=True, editable=False)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    #: PER-023: the links and the password are secrets of the person, and the rest is the state of the
    #: exchange. Neither belongs into the change log, which personnel planning reads.
    audit_exclude = frozenset(
        {
            "calendar_token",
            "caldav_password_encrypted",
            "caldav_synced_at",
            "caldav_error",
            "caldav_checked_at",
            "caldav_failures",
            "caldav_dirty",
            # API-015: the moments of the changes the log holds anyway.
            "phone_changed_at",
            "email_changed_at",
            "share_phone_changed_at",
            "share_email_changed_at",
        }
    )

    #: API-015: the contact data a person keeps themselves (PER-019), each with ``<name>_changed_at``.
    CONTACT_FIELDS = ("phone", "email", "share_phone", "share_email")

    class Meta:
        verbose_name = _("person")
        verbose_name_plural = _("people")
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        """First and last name as one text."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def sort_name(self) -> str:
        """``Last name, first name`` – for lists sorted by last name."""
        return f"{self.last_name}, {self.first_name}".strip(", ")

    @property
    def is_freelancer(self) -> bool:
        """Whether the fields for freelancers apply (PER-003)."""
        return self.kind == EmploymentKind.FREELANCER

    def clean(self) -> None:
        """Tidy the texts; the e-mail address is the account's too and must be free (AUT-026)."""
        super().clean()
        self.first_name = (self.first_name or "").strip()
        self.last_name = (self.last_name or "").strip()
        self.email = (self.email or "").strip().lower()
        if self.user_id and Person.objects.exclude(pk=self.pk).filter(user_id=self.user_id).exists():
            raise ValidationError({"user": _("This user account is already linked to another person.")})
        if self.email:
            from rentalars.accounts.models import User

            others = User.objects.filter(email__iexact=self.email)
            if self.user_id:
                others = others.exclude(pk=self.user_id)
            if others.exists():
                raise ValidationError({"email": _("This e-mail address is already used by another user.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the person and keep the account in step: create it for a new person (AUT-026).

        API-015: a contact field whose value changes notes the moment
        (``<name>_changed_at``) – now, or the moment given in
        ``contact_change_times`` (the companion app's offline change, judged
        by ``personnel.own_api``). A field that keeps its value keeps its
        moment; a new person starts with the moment of its creation.
        """
        from rentalars.accounts.models import User

        noted = self._note_contact_changes(kwargs.get("update_fields"))
        if noted and kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], *noted}
        syncing = getattr(self, "_syncing_account", False)
        self._syncing_account = False
        if not self.user_id:
            user = User(
                username=unique_username(self.first_name, self.last_name),
                email=self.email or None,
                first_name=self.first_name,
                last_name=self.last_name,
                is_active=self.is_active,
            )
            user.set_unusable_password()
            user._person_follows = True
            user.save()
            role_name = "Freie Kraft" if self.kind == EmploymentKind.FREELANCER else "Crew"
            from rentalars.accounts.models import Role
            from rentalars.core.start_data import role_names

            # UIX-029: the start roles of an English installation are "Freelancer" and "Crew".
            user.roles.set(Role.objects.filter(name__in=role_names(role_name)))
            self.user = user
            super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)
        if syncing or self.anonymised_at:
            return
        User.objects.filter(pk=self.user_id).exclude(
            first_name=self.first_name, last_name=self.last_name, email=self.email or None, is_active=self.is_active
        ).update(
            first_name=self.first_name, last_name=self.last_name, email=self.email or None, is_active=self.is_active
        )
        # The cached account of this instance (``person.user``) must show the same.
        cached = self._state.fields_cache.get("user")
        if cached is not None:
            cached.first_name, cached.last_name = self.first_name, self.last_name
            cached.email, cached.is_active = self.email or None, self.is_active

    def _note_contact_changes(self, update_fields: Any = None) -> list[str]:
        """Set ``<name>_changed_at`` of every contact field that changes with this save (API-015).

        Returns the names of the moments set, for ``update_fields``. The
        values before come from the snapshot of the change log
        (:meth:`AuditedModel._audit_before`); without one, from the database.
        """
        given: dict[str, datetime.datetime] = getattr(self, "contact_change_times", None) or {}
        self.contact_change_times: dict[str, datetime.datetime] = {}
        now = timezone.now()
        if self._state.adding:
            for name in self.CONTACT_FIELDS:
                if getattr(self, f"{name}_changed_at") is None:
                    setattr(self, f"{name}_changed_at", given.get(name) or now)
            return []
        names = [
            name
            for name in self.CONTACT_FIELDS
            if name in self.__dict__ and (update_fields is None or name in update_fields)
        ]
        before = self._audit_before() or {}
        if any(name not in before for name in names):
            before = {**before, **(type(self)._base_manager.filter(pk=self.pk).values(*names).first() or {})}
        noted = []
        for name in names:
            if name in before and before[name] == self.__dict__[name]:
                continue
            setattr(self, f"{name}_changed_at", given.get(name) or now)
            noted.append(f"{name}_changed_at")
        return noted


def unique_username(first_name: str, last_name: str) -> str:
    """A free username from a name: ``anna.becker``, then ``anna.becker2`` … (AUT-026)."""
    from django.utils.text import slugify

    from rentalars.accounts.models import User

    replacements = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
    parts = [slugify(part.translate(replacements)).replace("-", ".") for part in (first_name, last_name) if part]
    base = ".".join(part for part in parts if part)[:140] or "person"
    candidate, number = base, 1
    while User.objects.filter(username__iexact=candidate).exists():
        number += 1
        candidate = f"{base}{number}"
    return candidate


class PersonJobFunction(AuditedModel):
    """One person in one job function, with the rates from a day on (PER-005, PER-007, PER-029).

    A person has a job function as soon as one such row exists. Hourly rate,
    day rate and "valid from" are optional (PER-029): a row without rates
    only says that the person can be planned in the function – the costs
    then come from the guide values of the function. A row without "valid
    from" counts from always; there is at most one such row per person and
    function.

    A new rate is a new row with a later ``valid_from``; the old row stays,
    so that it is always clear what applied when. The row that applies on a
    day is the one with the latest "valid from" not after that day, else the
    row without a date, else the earliest row (see
    :func:`rentalars.personnel.services.rate_for`). That row counts as a
    whole: its empty rate means "no own rate from that day on", not "the
    rate of the row before". Changing a rate never reaches crew lines and
    time entries that exist already: they carry their own copy of the rate
    (PRJ-021, ZEI-008).

    Example::

        Tontechnik   –        –        always
        Tontechnik   35,00    280,00   from 01.01.2026
        Tontechnik   38,00    300,00   from 01.07.2026    <- applies from July on
        Stagehand    20,00    –        always
    """

    person = models.ForeignKey(Person, verbose_name=_("person"), on_delete=models.CASCADE, related_name="rates")
    job_function = models.ForeignKey(
        JobFunction, verbose_name=_("job function"), on_delete=models.PROTECT, related_name="rates"
    )
    hourly_rate = models.DecimalField(
        _("hourly rate"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    # PER-009, PER-029: what a day of the person costs, for crew lines charged per day.
    daily_rate = models.DecimalField(
        _("day rate"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    # PER-035: what an hour beyond the limit of hours per day of the service product costs.
    hourly_rate_above_limit = models.DecimalField(
        _("hourly rate from the limit"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    valid_from = models.DateField(_("valid from"), null=True, blank=True)

    audit_sensitive = {
        "hourly_rate": SpecialRight.PERSONNEL_COSTS,
        "daily_rate": SpecialRight.PERSONNEL_COSTS,
        "hourly_rate_above_limit": SpecialRight.PERSONNEL_COSTS,
    }

    class Meta:
        # A row can hold a day rate or no rate at all (PER-029): it is the job function of the person.
        verbose_name = _("job function and rates")
        verbose_name_plural = _("job functions and rates")
        ordering = ["job_function__name", models.F("valid_from").desc(nulls_last=True)]
        constraints = [
            # A NULL "valid from" is not caught by this on any database; ``clean`` checks the row without a date.
            models.UniqueConstraint(fields=["person", "job_function", "valid_from"], name="person_rate_unique_per_day"),
        ]

    def __str__(self) -> str:
        since = f"{self.valid_from:{local_pattern('%d.%m.%Y')}}" if self.valid_from else str(_("always"))
        return f"{self.person} – {self.job_function} ({since})"

    def audit_parent(self) -> models.Model | None:
        """Show rate changes in the history of the person."""
        return self.person

    def clean(self) -> None:
        """PER-029: one row without "valid from" per person and job function."""
        super().clean()
        if self.valid_from is None and self.person_id and self.job_function_id:
            others = PersonJobFunction.objects.filter(
                person_id=self.person_id, job_function_id=self.job_function_id, valid_from__isnull=True
            ).exclude(pk=self.pk)
            if others.exists():
                raise ValidationError(
                    {"valid_from": _("This job function already has rates without a date; change those instead.")}
                )


class AbsenceKind(models.TextChoices):
    """Why somebody is not available (PER-011)."""

    VACATION = "vacation", _("holiday")
    SICK = "sick", _("sick")
    UNAVAILABLE = "unavailable", _("not available")


class Absence(AuditedModel):
    """A period in which a person cannot be planned (PER-011)."""

    person = models.ForeignKey(Person, verbose_name=_("person"), on_delete=models.CASCADE, related_name="absences")
    kind = models.CharField(_("kind"), max_length=12, choices=AbsenceKind.choices, default=AbsenceKind.UNAVAILABLE)
    start = models.DateTimeField(_("from"))
    end = models.DateTimeField(_("until"))
    note = models.CharField(_("note"), max_length=250, blank=True)

    class Meta:
        verbose_name = _("absence")
        verbose_name_plural = _("absences")
        ordering = ["start"]
        indexes = [models.Index(fields=["person", "start", "end"], name="absence_person_period_idx")]

    def __str__(self) -> str:
        return f"{self.person}: {self.get_kind_display()} {self.start:{local_pattern('%d.%m.%Y')}}–{self.end:{local_pattern('%d.%m.%Y')}}"

    def audit_parent(self) -> models.Model | None:
        """Show absences in the history of the person."""
        return self.person

    def clean(self) -> None:
        """The end must be after the start."""
        super().clean()
        errors: dict[str, Any] = {}
        if self.start and self.end and self.end <= self.start:
            errors["end"] = _("The end must be after the start.")
        if errors:
            raise ValidationError(errors)


class QualificationType(AuditedModel):
    """A kind of qualification or certificate, e.g. "Hubarbeitsbühne (IPAF 3a)" (PER-014).

    Maintained as master data. ``validity_months`` suggests the expiry date
    when a qualification is recorded (a first-aid course counts two years);
    empty means it does not expire by itself.
    """

    name = models.CharField(_("name"), max_length=120, unique=True)
    description = models.TextField(_("description"), blank=True)
    validity_months = models.PositiveSmallIntegerField(
        _("valid for months"), null=True, blank=True, help_text=_("Empty: does not expire by itself.")
    )
    #: LOG-012: a driving licence – the classes it allows to drive, e.g. "B, BE".
    licence_classes = models.CharField(
        _("driving licence classes"),
        max_length=60,
        blank=True,
        help_text=_("Only for a driving licence: the classes it covers, separated by commas, e.g. B, BE."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("qualification type")
        verbose_name_plural = _("qualification types")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """LOG-012: the classes in capitals, one comma and space between them."""
        super().clean()
        self.licence_classes = ", ".join(self.covered_classes)

    @property
    def covered_classes(self) -> list[str]:
        """LOG-012: the driving licence classes this qualification covers, in capitals: ``["B", "BE"]``."""
        parts = (self.licence_classes or "").replace(";", ",").split(",")
        return [part.strip().upper() for part in parts if part.strip()]


def qualification_file_path(instance: Qualification, filename: str) -> str:
    """Store certificates in a folder per person, under a random name (see ``project_file_path``)."""
    import secrets
    from pathlib import Path

    return f"qualifications/{instance.person_id}/{secrets.token_hex(12)}{Path(filename).suffix.lower()[:10]}"


class Qualification(AuditedModel):
    """A qualification of one person with its expiry date and the certificate (PER-014).

    One record per person and type: a renewed certificate replaces the
    old one, and the change log keeps the earlier dates. Qualifications are
    personnel data – only those who may read the personnel module see them
    (NFA-010); the person sees their own under "My profile".
    """

    #: Days before the expiry date in which a qualification counts as "expiring soon".
    SOON_DAYS = 60

    person = models.ForeignKey(
        Person, verbose_name=_("person"), on_delete=models.CASCADE, related_name="qualifications"
    )
    qualification_type = models.ForeignKey(
        QualificationType, verbose_name=_("qualification"), on_delete=models.PROTECT, related_name="qualifications"
    )
    detail = models.CharField(
        _("details"), max_length=200, blank=True, help_text=_("e.g. the classes of a driving licence: B, BE, C1E")
    )
    acquired_on = models.DateField(_("acquired on"), null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True, help_text=_("Empty: does not expire."))
    document = models.FileField(_("certificate"), upload_to=qualification_file_path, blank=True, max_length=200)
    document_name = models.CharField(_("file name"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("qualification")
        verbose_name_plural = _("qualifications")
        ordering = ["qualification_type__name"]
        constraints = [
            models.UniqueConstraint(fields=["person", "qualification_type"], name="qualification_once_per_person")
        ]

    def __str__(self) -> str:
        return f"{self.person}: {self.qualification_type}"

    def audit_parent(self) -> models.Model | None:
        """Show qualifications in the history of the person."""
        return self.person

    def clean(self) -> None:
        """An expiry date before the date it was acquired is a typing error."""
        super().clean()
        if self.acquired_on and self.valid_until and self.valid_until < self.acquired_on:
            raise ValidationError({"valid_until": _("The qualification cannot expire before it was acquired.")})

    @property
    def state(self) -> str:
        """``valid``, ``soon`` (expires within :data:`SOON_DAYS`) or ``expired``."""
        if self.valid_until is None:
            return "valid"
        today = timezone.localdate()
        if self.valid_until < today:
            return "expired"
        if self.valid_until <= today + datetime.timedelta(days=self.SOON_DAYS):
            return "soon"
        return "valid"


class AvailabilityState(models.TextChoices):
    """How available somebody says they are (PER-021): green, yellow, red."""

    AVAILABLE = "available", _("available")
    LIMITED = "limited", _("available with limits")
    UNAVAILABLE = "unavailable", _("not available")


class AvailabilitySource(models.TextChoices):
    """Where a mark comes from (PER-021, PER-022)."""

    OWN = "own", _("entered")
    FEED = "feed", _("from the linked calendar")


class AvailabilityRepeat(models.TextChoices):
    """How an availability entered as a series repeats (PER-028)."""

    DAILY = "daily", _("daily")
    WEEKLY = "weekly", _("weekly")
    MONTHLY = "monthly", _("monthly")


class AvailabilitySeries(models.Model):
    """An availability entered once for many days: "every Tuesday and Thursday evening red" (PER-028).

    The series is the rule; its occurrences are stored as ordinary own
    :class:`AvailabilityMark` rows pointing to it, up to one year ahead.
    They are painted like any other entry – they replace what was entered
    in their period, and what is entered later replaces them. Changing the
    series paints its occurrences anew from the day of the change on;
    removing it removes them, all or from a day on.

    The first occurrence is ``first_day`` to ``last_day`` – whole days, or
    with ``start_time``/``end_time`` the same times on each of these days.
    It repeats every ``interval`` days, weeks (on ``weekdays``, Monday = 0)
    or months (on the same day of the month), until ``until`` or ``count``
    times.
    """

    person = models.ForeignKey(
        Person, verbose_name=_("person"), on_delete=models.CASCADE, related_name="availability_series"
    )
    state = models.CharField(_("availability"), max_length=12, choices=AvailabilityState.choices)
    note = models.CharField(_("note"), max_length=250, blank=True)
    first_day = models.DateField(_("first day"))
    last_day = models.DateField(_("last day"))
    start_time = models.TimeField(_("from (time)"), null=True, blank=True)
    end_time = models.TimeField(_("until (time)"), null=True, blank=True)
    repeat = models.CharField(_("repeat"), max_length=8, choices=AvailabilityRepeat.choices)
    interval = models.PositiveSmallIntegerField(_("every"), default=1)
    #: Weekdays of a weekly series, Monday = 0, as "0,2,4".
    weekdays = models.CharField(_("weekdays"), max_length=20, blank=True)
    until = models.DateField(_("until"), null=True, blank=True)
    count = models.PositiveSmallIntegerField(_("times"), null=True, blank=True)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("availability series")
        verbose_name_plural = _("availability series")
        ordering = ["first_day", "pk"]

    def __str__(self) -> str:
        return f"{self.person}: {self.get_state_display()} {self.get_repeat_display()} {self.first_day:{local_pattern('%d.%m.%Y')}}"

    @property
    def weekday_numbers(self) -> list[int]:
        """The weekdays of a weekly series as numbers, Monday = 0."""
        return sorted({int(part) for part in self.weekdays.split(",") if part.strip().isdigit() and int(part) < 7})


class CalendarFeed(models.Model):
    """A linked calendar of a person: an .ics address whose busy times count as "not available" (PER-022, PER-031).

    A person may link several calendars – the private one, the one of the
    band, the one of the other employer. Each is read on its own, every
    :data:`~rentalars.personnel.calendars.FEED_INTERVAL`, and keeps its own
    state: when it was last read, what went wrong, how often in a row. Their
    busy times together are one layer of the availability ("busy in the
    linked calendar", PER-027): a reading replaces the busy times of that
    calendar only, so a calendar that cannot be read keeps its last busy
    times and leaves those of the others alone.

    The address is a secret of the person: the private link of a calendar
    shows all its appointments. Only the person sees it; personnel planning
    sees the server (:attr:`host`) and the name the person gave it. It never
    enters the change log, the data export or the API answers for others.
    """

    #: The most calendars one person can link.
    MAX_PER_PERSON = 10

    person = models.ForeignKey(
        Person, verbose_name=_("person"), on_delete=models.CASCADE, related_name="calendar_feeds"
    )
    url = models.URLField(_("address of the calendar (ICS link)"), max_length=500)
    label = models.CharField(
        _("name"), max_length=80, blank=True, help_text=_("Only for telling the calendars apart, e.g. “Band”.")
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    # How the reading goes; written with ``update()`` by ``personnel.calendars`` only.
    checked_at = models.DateTimeField(_("last read"), null=True, blank=True, editable=False)
    error = models.CharField(_("problem with the calendar"), max_length=250, blank=True, editable=False)
    failures = models.PositiveSmallIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = _("linked calendar")
        verbose_name_plural = _("linked calendars")
        ordering = ["created_at", "pk"]
        constraints = [models.UniqueConstraint(fields=["person", "url"], name="calendar_feed_once_per_person")]

    def __str__(self) -> str:
        return f"{self.person_id}: {self.name}"

    @property
    def host(self) -> str:
        """Only the server of the address – what others than the person get to see of it."""
        from urllib.parse import urlsplit

        return urlsplit(self.url).hostname or ""

    @property
    def name(self) -> str:
        """The name the person gave the calendar, else its server."""
        return self.label or self.host


class AvailabilityMark(models.Model):
    """A period a person marked as available, available with limits or not available (PER-021).

    Entered by the person on the own availability calendar, or read from one
    of the linked calendars (:class:`CalendarFeed`, PER-022, PER-031) – those
    are replaced with every reading of their calendar and never edited by
    hand. Unlike an
    :class:`Absence`, which the personnel planning enters, marks are the
    person's own statement; "not available" warns when planning, "with
    limits" hints.

    At any moment a person has one availability (PER-027): own entries never
    overlap each other, and where a busy time of the linked calendar meets an
    own entry, the newer statement counts – ``entered_at``. See
    :func:`rentalars.personnel.marks.resolve`.
    """

    person = models.ForeignKey(
        Person, verbose_name=_("person"), on_delete=models.CASCADE, related_name="availability_marks"
    )
    start = models.DateTimeField(_("from"))
    end = models.DateTimeField(_("until"))
    state = models.CharField(_("availability"), max_length=12, choices=AvailabilityState.choices)
    note = models.CharField(_("note"), max_length=250, blank=True)
    source = models.CharField(
        _("source"), max_length=8, choices=AvailabilitySource.choices, default=AvailabilitySource.OWN
    )
    #: The linked calendar a busy time comes from (PER-031); empty for own entries.
    feed = models.ForeignKey(
        CalendarFeed,
        verbose_name=_("linked calendar"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="marks",
        editable=False,
    )
    #: The UID of the appointment with its start, after the ID of its calendar: "4:abc@mail.example#2027-03-10T…".
    feed_uid = models.CharField(max_length=255, blank=True, editable=False)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    #: When the statement was made (PER-027): an own entry when it was entered – a piece left over
    #: from cutting keeps the time of its entry –, a busy time when the appointment was last changed
    #: in the linked calendar (``LAST-MODIFIED``, else ``CREATED``); empty if the calendar does not say.
    entered_at = models.DateTimeField(_("entered"), null=True, blank=True, editable=False)
    series = models.ForeignKey(
        AvailabilitySeries,
        verbose_name=_("series"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marks",
        editable=False,
    )

    class Meta:
        verbose_name = _("availability")
        verbose_name_plural = _("availabilities")
        ordering = ["start"]
        indexes = [models.Index(fields=["person", "start", "end"], name="availability_person_period_idx")]

    def __str__(self) -> str:
        return f"{self.person}: {self.get_state_display()} {self.start:{local_pattern('%d.%m.%Y %H:%M')}}–{self.end:{local_pattern('%d.%m.%Y %H:%M')}}"

    def clean(self) -> None:
        """The end must be after the start."""
        super().clean()
        if self.start and self.end and self.end <= self.start:
            raise ValidationError({"end": _("The end must be after the start.")})


class CalendarPush(models.Model):
    """One deployment as it was last written into the CalDAV calendar of a person (PER-023).

    Rentalars writes only what changed and removes what is no longer planned;
    this row remembers what the server has.
    """

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="calendar_pushes")
    uid = models.CharField(max_length=255)
    href = models.CharField(max_length=500)
    etag = models.CharField(max_length=255, blank=True)
    digest = models.CharField(max_length=64)
    pushed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["person", "uid"], name="calendar_push_unique_uid")]

    def __str__(self) -> str:
        return f"{self.person_id}: {self.uid}"


# PER-038: the price offers of freelancers – models in a file of their own, imported here so that Django finds them.
from rentalars.personnel.offer_models import OfferSettings, PriceOffer  # noqa: E402, F401
