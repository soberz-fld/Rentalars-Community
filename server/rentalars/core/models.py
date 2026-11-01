# SPDX-License-Identifier: GPL-3.0-or-later
"""Models of the ``core`` module: settings, number ranges and the audit log."""

from __future__ import annotations

import datetime
import secrets
from contextvars import ContextVar
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel
from rentalars.core.holidays import STATE_CHOICES, OwnHolidaySpec  # PER-009, PER-040
from rentalars.core.i18n import LANGUAGE_CHOICES, installation_language  # UIX-029
from rentalars.core.uploads import validate_image_upload

#: Rows of singleton tables read during the current request (``None`` outside requests).
_request_cache: ContextVar[dict[Any, Any] | None] = ContextVar("rentalars_singletons", default=None)


def start_request_cache() -> Any:
    """Begin keeping singleton rows for one request; returns the token to end it with."""
    return _request_cache.set({})


def end_request_cache(token: Any) -> None:
    """Forget the rows kept for the request."""
    _request_cache.reset(token)


class SingletonModel(AuditedModel):
    """A table that holds exactly one row, e.g. the company profile.

    The row always has the primary key 1. ``load()`` creates it on first use,
    so code never has to check whether the settings exist.
    """

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Force the single row and save it."""
        self.pk = 1
        self._state.adding = not type(self).objects.filter(pk=1).exists()
        super().save(*args, **kwargs)
        cache = _request_cache.get()
        if cache is not None:
            cache[type(self)] = self

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Refuse deletion: the application expects the row to exist."""
        raise ValidationError(_("This record cannot be deleted."))

    @classmethod
    def load(cls) -> Any:
        """Return the single row, creating it with defaults if necessary.

        Within a request the row is read once and then kept (see
        :class:`~rentalars.core.middleware.RequestCacheMiddleware`): the
        settings are asked for by several parts of every page.
        """
        cache = _request_cache.get()
        if cache is not None and cls in cache:
            return cache[cls]
        instance = cls.objects.filter(pk=1).first()
        if instance is None:
            instance = cls(pk=1)
            instance.save()
        if cache is not None:
            cache[cls] = instance
        return instance


class CompanyProfile(SingletonModel):
    """The company's own data, printed on documents such as the packlist (ADM-001)."""

    name = models.CharField(_("company name"), max_length=200, blank=True)
    street = models.CharField(_("street and number"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    country = models.CharField(_("country"), max_length=80, blank=True, default="Deutschland")
    phone = models.CharField(_("phone"), max_length=60, blank=True)
    email = models.EmailField(_("e-mail"), blank=True)
    website = models.CharField(_("website"), max_length=200, blank=True)
    tax_number = models.CharField(_("tax number"), max_length=60, blank=True)
    vat_id = models.CharField(_("VAT identification number"), max_length=30, blank=True)
    bank_name = models.CharField(_("bank"), max_length=120, blank=True)
    iban = models.CharField(_("IBAN"), max_length=42, blank=True)
    bic = models.CharField(_("BIC"), max_length=11, blank=True)
    logo = models.ImageField(
        _("logo"),
        upload_to="company/",
        blank=True,
        validators=[validate_image_upload],
        help_text=_("PNG or JPEG, at most 2 MB."),
    )
    # --- Documents (DOK-005, DOK-006) ---------------------------------------
    register_details = models.CharField(
        _("register and management"),
        max_length=250,
        blank=True,
        help_text=_(
            "Printed in the footer of documents, e.g. “Amtsgericht Musterstadt HRB 1234 · Managing director: …”"
        ),
    )
    payment_terms_days = models.PositiveSmallIntegerField(
        _("payment terms in days"), default=14, help_text=_("For invoices, unless the customer has terms of its own.")
    )
    # PRJ-097: where the trips of a project start and end – in one line, for the route links.
    warehouse_address = models.CharField(
        _("address of the warehouse"),
        max_length=250,
        blank=True,
        help_text=_(
            "Where the trips of the projects start and end, in one line, e.g. “5 Harbour Road, 12345 Sampletown”."
            " Empty: the address of the company."
        ),
    )
    # UIX-029: the language of the documents to customers – one for the whole company.
    document_language = models.CharField(
        _("language of documents"),
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default=installation_language,
        help_text=_(
            "Offers, order confirmations, delivery notes, invoices and packing lists, and the mails Rentalars "
            "writes to customers by itself. Only the fixed texts follow this language: what you typed yourself – "
            "document templates, text blocks, mail templates, product names – stays as you wrote it."
        ),
    )

    class Meta:
        verbose_name = _("company profile")
        verbose_name_plural = _("company profile")

    def __str__(self) -> str:
        return self.name or str(_("Company profile"))

    @property
    def address_lines(self) -> list[str]:
        """The postal address as printable lines, without empty ones."""
        lines = [self.street, f"{self.postal_code} {self.city}".strip()]
        return [line for line in lines if line]

    @property
    def address_one_line(self) -> str:
        """UIX-033: the company's address in one line, as a route planner takes it; empty without street and city.

        The country alone is no address: a trip would start "in Deutschland" (PRJ-097).
        """
        lines = self.address_lines
        return ", ".join(part for part in (*lines, self.country) if part) if lines else ""

    @property
    def warehouse_one_line(self) -> str:
        """PRJ-097: where trips start and end – the warehouse address, else the company's own."""
        return " ".join(self.warehouse_address.split()) or self.address_one_line


#: ADM-014: the help text of ``SystemSettings.mail_tag_prefix`` with a project number of today, without "P-"
#: (in the database state since core 0009).
MAIL_TAG_PREFIX_HELP = _(
    "The tag reads [RL#2026-0042] with the prefix RL. Changing it, answers to older mails still need the old one."
)


class SystemSettings(SingletonModel):
    """Settings an administrator changes in the browser (ADM-004)."""

    setup_completed = models.BooleanField(_("first-run setup completed"), default=False)
    defaults_installed = models.BooleanField(_("start data installed"), default=False)
    setup_token = models.CharField(
        _("setup token"),
        max_length=64,
        blank=True,
        help_text=_("Protects the first-run setup on a server; empty in development."),
    )

    # VFG-005: time before and after each use during which material counts as
    # occupied (checking, cleaning, loading). 0 means "no buffer".
    buffer_before_hours = models.DecimalField(
        _("buffer before use (hours)"),
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    buffer_after_hours = models.DecimalField(
        _("buffer after use (hours)"),
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    # PRJ-068: a new project runs from noon to noon of the next day – the usual rental day.
    default_start_time = models.TimeField(_("usual start time"), default=datetime.time(12, 0))
    default_end_time = models.TimeField(
        _("usual end time"),
        default=datetime.time(12, 0),
        help_text=_("Not after the start time: the project ends on the following day."),
    )

    # AUT-003 and AUT-005
    password_min_length = models.PositiveSmallIntegerField(
        _("minimum password length"),
        default=10,
        validators=[MinValueValidator(8), MaxValueValidator(128)],
    )
    login_max_attempts = models.PositiveSmallIntegerField(
        _("failed logins before lockout"),
        default=5,
        validators=[MinValueValidator(3), MaxValueValidator(50)],
    )
    login_lockout_minutes = models.PositiveSmallIntegerField(
        _("lockout duration (minutes)"),
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(24 * 60)],
    )

    # PER-010: everybody may see their own hourly rates, unless switched off here.
    people_see_own_rates = models.BooleanField(
        _("people may see their own hourly rates"),
        default=True,
        help_text=_(
            "Applies to accounts without the right to see personnel costs: in their own times and deployments."
        ),
    )
    # PER-034: new times of a crew line that was asked for or accepted are asked for again.
    ask_again_on_new_times = models.BooleanField(
        _("ask again when the times change"),
        default=True,
        help_text=_(
            "When the times of a crew line that was asked for or accepted change, the person gets a new request "
            "and the line shows “asked” again until the answer comes. Not for declined lines."
        ),
    )
    # DOK-014: whoever writes invoices in another program switches them off here.
    invoices_enabled = models.BooleanField(
        _("use Rentalars as accounting software"),
        default=True,
        help_text=_(
            "On: Rentalars is your accounting program – it makes the invoices and cancellations, takes in the "
            "incoming invoices and hands them over to Lexware Office or the DATEV export. Off: no invoice and no "
            "cancellation can be made, and handing them over is hidden. Invoices made before stay readable with "
            "their projects; projects are closed without an invoice."
        ),
    )

    # ZEI-018: hints at conspicuous time entries, after the German working time act (ArbZG §§ 3–5).
    # Never blocking; 0 switches a hint off. All of them are switched on and off at once.
    time_hints_enabled = models.BooleanField(
        _("show hints at working times"),
        default=True,
        help_text=_(
            "Long working day, short break, short rest – where times are entered, in the approval, the report "
            "and the API. Off: no hints anywhere; the limits below are kept."
        ),
    )
    time_hint_day_hours = models.DecimalField(
        _("hint: working day longer than … hours"),
        max_digits=4,
        decimal_places=1,
        default=Decimal("10"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))],
        help_text=_("The hours of work of one person on one working day, breaks not counted. 0: no hint."),
    )
    time_hint_break_hours = models.DecimalField(
        _("hint: a break is due after more than … hours of work"),
        max_digits=4,
        decimal_places=1,
        default=Decimal("6"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))],
    )
    time_hint_break_minutes = models.PositiveSmallIntegerField(
        _("hint: that break lasts at least … minutes"),
        default=30,
        validators=[MaxValueValidator(600)],
        help_text=_("The recorded breaks and the gaps between the entries of the day count. 0: no hint."),
    )
    time_hint_long_break_hours = models.DecimalField(
        _("hint: a longer break is due after more than … hours of work"),
        max_digits=4,
        decimal_places=1,
        default=Decimal("9"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))],
    )
    time_hint_long_break_minutes = models.PositiveSmallIntegerField(
        _("hint: the longer break lasts at least … minutes"), default=45, validators=[MaxValueValidator(600)]
    )
    time_hint_rest_hours = models.DecimalField(
        _("hint: rest between two working days shorter than … hours"),
        max_digits=4,
        decimal_places=1,
        default=Decimal("11"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))],
        help_text=_("0: no hint."),
    )
    # ZEI-019: a trip with the own car costs kilometres × this rate.
    expense_km_rate = models.DecimalField(
        _("travel costs per kilometre"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.30"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("10"))],
        help_text=_("For trips with the own car entered as expenses. A trip keeps the rate it was recorded with."),
    )
    # ZEI-027: the way to work of a person (``Person.commute_km``) is deducted from trips by kilometre.
    expense_deduct_commute = models.BooleanField(
        _("deduct the way to work from trips"),
        default=True,
        help_text=_(
            "Twice the distance home – company of the person is deducted once a day per project from trips by "
            "kilometre. Trips recorded before keep their amount."
        ),
    )

    # AUT-008: sessions end after this much time without a request.
    session_idle_minutes = models.PositiveIntegerField(
        _("log out after … minutes without activity"),
        default=240,
        validators=[MinValueValidator(5), MaxValueValidator(7 * 24 * 60)],
    )
    # NFA-049: for operation from the internet.
    two_factor_for_administrators = models.BooleanField(
        _("two-factor login required for administrators"),
        default=False,
        help_text=_("Everybody who may change the settings, and every account with all rights."),
    )
    # EML-009: the prefix of the tag that assigns mails to projects, system-wide.
    mail_tag_prefix = models.CharField(
        _("prefix of the project tag in mails"),
        max_length=10,
        default="RL",
        validators=[RegexValidator(r"^[A-Za-z0-9]+$", _("Letters and digits only."))],
        help_text=MAIL_TAG_PREFIX_HELP,
    )
    # NFA-007, PRJ-007: the largest file that can be uploaded.
    max_upload_mb = models.PositiveSmallIntegerField(
        _("largest file to upload (MB)"), default=50, validators=[MinValueValidator(1), MaxValueValidator(500)]
    )
    # UIX-034, NFA-050: a map loads only after a click unless this says otherwise.
    maps_load_at_once = models.BooleanField(
        _("load maps at once"),
        default=False,
        help_text=_(
            "Off: a map appears after a click on “Show map”; only then is the address sent to OpenStreetMap and "
            "the map loaded. On: every page with an address shows its map right away."
        ),
    )

    # API-011: how many calls one API token may make per minute.
    api_requests_per_minute = models.PositiveIntegerField(
        _("API calls per token and minute"),
        default=600,
        validators=[MaxValueValidator(100_000)],
        help_text=_("More calls are answered with “too many requests” until the minute is over. 0: no limit."),
    )

    # NFA-011: how long records are kept. 0 keeps them for good.
    retention_security_log_days = models.PositiveIntegerField(
        _("keep the security log (days)"),
        default=365,
        validators=[MinValueValidator(30), MaxValueValidator(3650)],
        help_text=_("Logins, failed logins, changes to users and roles."),
    )
    retention_change_log_days = models.PositiveIntegerField(
        _("keep the change log (days)"),
        default=0,
        validators=[MaxValueValidator(36500)],
        help_text=_("Who changed what and when. 0: for good."),
    )
    retention_notifications_days = models.PositiveIntegerField(
        _("keep notifications (days)"), default=180, validators=[MinValueValidator(7), MaxValueValidator(3650)]
    )
    retention_jobs_days = models.PositiveIntegerField(
        _("keep results of background tasks (days)"),
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text=_("Imports, labels, full exports – with their files."),
    )
    # AUT-028: who read which personal data, for the data-protection officer.
    retention_access_log_days = models.PositiveIntegerField(
        _("keep the access log (days)"),
        default=180,
        validators=[MinValueValidator(30), MaxValueValidator(3650)],
        help_text=_("Who opened or downloaded customers, people, projects, exports and backups."),
    )

    audit_exclude = frozenset({"setup_token"})

    class Meta:
        verbose_name = _("system settings")
        verbose_name_plural = _("system settings")

    def __str__(self) -> str:
        return str(_("System settings"))

    def new_setup_token(self) -> str:
        """Create, store and return a fresh token for the first-run setup."""
        self.setup_token = secrets.token_urlsafe(24)
        self.save()
        return self.setup_token


class NumberRangeKey(models.TextChoices):
    """The number ranges the system knows (ADM-003)."""

    PROJECT = "project", _("Projects")
    CUSTOMER = "customer", _("Customers")
    MATERIAL_ITEM = "material_item", _("Material IDs")
    DOCUMENT = "document", _("Documents")
    # DOK-005: each kind of document counts on its own; invoices without gaps (§ 14 UStG).
    OFFER = "offer", _("Offers")  # DOK-010
    ORDER_CONFIRMATION = "order_confirmation", _("Order confirmations")
    DELIVERY_NOTE = "delivery_note", _("Delivery notes")
    INVOICE = "invoice", _("Invoices and cancellations")
    CREW_SHEET = "crew_sheet", _("Crew dispositions")


class NumberRange(AuditedModel):
    """A counter that hands out consecutive numbers (ADM-003).

    A number is built from ``prefix`` and the counter padded with leading
    zeros to ``min_digits``. The prefix may contain ``{year}``.

    ==========  ===========  ==========  ============  ==============
    range       prefix       min_digits  yearly reset  example
    ==========  ===========  ==========  ============  ==============
    project     {year}-      4           yes           2026-0042
    customer    (empty)      5           no            10001
    material    (empty)      4           no            0001 … 10000
    ==========  ===========  ==========  ============  ==============

    A project keeps its number
    when the prefix is changed later (ADM-014).

    The material ID is a pure number (MAT-003), so its range has no prefix.
    After 9999 the counter simply continues with 10000: the padding is a
    minimum, not a limit.
    """

    key = models.CharField(_("range"), max_length=30, unique=True, choices=NumberRangeKey.choices)
    prefix = models.CharField(
        _("prefix"),
        max_length=30,
        blank=True,
        help_text=_("Text in front of the number. {year} is replaced by the current year."),
    )
    min_digits = models.PositiveSmallIntegerField(
        _("minimum number of digits"),
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    start_value = models.PositiveIntegerField(_("start value"), default=1, validators=[MinValueValidator(1)])
    next_value = models.PositiveIntegerField(_("next number"), default=1, validators=[MinValueValidator(1)])
    reset_yearly = models.BooleanField(_("restart every year"), default=False)
    current_year = models.PositiveSmallIntegerField(_("year of the counter"), null=True, blank=True)

    class Meta:
        verbose_name = _("number range")
        verbose_name_plural = _("number ranges")
        ordering = ["key"]

    def __str__(self) -> str:
        return self.get_key_display()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save; a counter somebody sets for a range that restarts every year belongs to the current year.

        Else the first number taken in a new year would throw the entered "next number 154" away and start at 1 – a
        number that may exist already.
        """
        if self.reset_yearly and self.pk:
            old = type(self).objects.filter(pk=self.pk).values("next_value", "reset_yearly").first()
            if old is not None and (old["next_value"] != self.next_value or not old["reset_yearly"]):
                self.current_year = timezone.localdate().year
        super().save(*args, **kwargs)

    def clean(self) -> None:
        """Enforce the rule that material IDs are pure numbers (MAT-003)."""
        super().clean()
        if self.key == NumberRangeKey.MATERIAL_ITEM and self.prefix:
            raise ValidationError({"prefix": _("Material IDs are pure numbers and cannot have a prefix.")})

    def format(self, value: int, year: int | None = None) -> str:
        """Return ``value`` as the printable number of this range.

        Example: prefix ``{year}-``, four digits, value 42, year 2026
        gives ``2026-0042``.
        """
        if year is None:
            year = timezone.localdate().year
        prefix = self.prefix.replace("{year}", str(year))
        return f"{prefix}{value:0{self.min_digits}d}"

    @property
    def preview(self) -> str:
        """What the next number of this range will look like."""
        return self.format(self.next_value)

    @classmethod
    def allocate(cls, key: str) -> tuple[int, str]:
        """Take the next number of a range.

        The row is locked while the counter is read and increased. Two users
        who create a project at the same moment therefore never receive the
        same number.

        The counter moving on is not written to the change log (hence
        ``update()`` instead of ``save()``): the project or item that got the
        number is logged, and one more line per number would only bury what
        people did. A change of the range by an administrator is logged.

        Args:
            key: One of :class:`NumberRangeKey`.

        Returns:
            The counter value and the formatted number, e.g. ``(42, "2026-0042")``.
        """
        with transaction.atomic():
            number_range = cls.objects.select_for_update().get(key=key)
            year = timezone.localdate().year
            if number_range.reset_yearly and number_range.current_year != year:
                # A counter that was never used (no year yet) belongs to this year – the number an
                # administrator entered ("next number 154") stands; only a counter of an earlier year starts again.
                if number_range.current_year is not None:
                    number_range.next_value = number_range.start_value
                number_range.current_year = year
            value = number_range.next_value
            cls.objects.filter(pk=number_range.pk).update(next_value=value + 1, current_year=number_range.current_year)
            return value, number_range.format(value, year)

    @classmethod
    def ensure_next_is_above(cls, key: str, highest_used: int) -> None:
        """Move the counter behind ``highest_used`` if it is not already there.

        Used after an import took over existing IDs (IMP-008): the next new
        ID must continue behind the highest imported one.
        """
        with transaction.atomic():
            number_range = cls.objects.select_for_update().get(key=key)
            if number_range.next_value <= highest_used:
                # Not logged, for the same reason as in allocate().
                cls.objects.filter(pk=number_range.pk).update(next_value=highest_used + 1)


class AuditAction(models.TextChoices):
    """What kind of change a log entry describes."""

    CREATED = "created", _("created")
    UPDATED = "updated", _("changed")
    DELETED = "deleted", _("deleted")
    EVENT = "event", _("event")


class AuditLogEntry(models.Model):
    """One line of the system-wide change log (ADM-005).

    Entries are written by :mod:`rentalars.core.audit` and never edited.
    ``changes`` maps a field name to ``[old value, new value]``; for events
    it holds the details of the event.
    """

    timestamp = models.DateTimeField(_("time"), default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    actor_label = models.CharField(_("user name"), max_length=150, blank=True)
    action = models.CharField(_("action"), max_length=10, choices=AuditAction.choices)
    event = models.CharField(_("event"), max_length=60, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    object_id = models.CharField(max_length=40)
    object_repr = models.CharField(_("object"), max_length=200)
    changes = models.JSONField(_("changes"), default=dict, blank=True)
    parent_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    parent_object_id = models.CharField(max_length=40, blank=True)

    class Meta:
        verbose_name = _("change log entry")
        verbose_name_plural = _("change log")
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="audit_object_idx"),
            models.Index(fields=["parent_content_type", "parent_object_id"], name="audit_parent_idx"),
            # (stock watch; R4-1) "The newest entry of a kind" (``stock_stamp``) is answered from this index.
            models.Index(fields=["content_type", "id"], name="audit_type_newest_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.actor_label} {self.action} {self.object_repr}"

    @classmethod
    def for_object(cls, instance: models.Model, *, include_children: bool = True) -> models.QuerySet[AuditLogEntry]:
        """Return the history of one object, newest first.

        Args:
            instance: The object whose history is wanted.
            include_children: Also return entries of objects that named
                ``instance`` as their audit parent (e.g. the lines of a
                project).
        """
        content_type = ContentType.objects.get_for_model(instance, for_concrete_model=True)
        own = models.Q(content_type=content_type, object_id=str(instance.pk))
        if include_children:
            own |= models.Q(parent_content_type=content_type, parent_object_id=str(instance.pk))
        return cls.objects.filter(own).select_related("actor", "content_type")


class ErrorRecord(models.Model):
    """An error of the application, counted per kind (NFA-018).

    Every unexpected error lands in the service log (journalctl) anyway. Here
    the same error is counted once with its first and last occurrence, so
    that the self-check can show it and the operators are told once, not a
    hundred times.
    """

    signature = models.CharField(max_length=64, unique=True)
    source = models.CharField(_("where"), max_length=200)
    message = models.TextField(_("error"))
    details = models.TextField(_("details"), blank=True)
    count = models.PositiveIntegerField(_("how often"), default=1)
    first_seen = models.DateTimeField(_("first"), default=timezone.now)
    last_seen = models.DateTimeField(_("last"), default=timezone.now)
    reported_at = models.DateTimeField(_("reported"), null=True, blank=True)

    class Meta:
        verbose_name = _("error")
        verbose_name_plural = _("errors")
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"{self.source}: {self.message[:80]}"


class TablePreference(models.Model):
    """The columns a user chose for a list (UIX-015) – and the number of entries per page (UIX-050; UIX-012).

    Not part of the change log: which columns somebody looks at is nobody
    else's business, and it changes often. A column that a later version no
    longer has is simply ignored when the choice is read.

    UIX-050: ``page_size`` is kept under the name of
    the list's page (``core.listing.list_key``, e.g. ``products:list``); the
    columns under the key of the table (``products``). A row may hold either.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="table_preferences")
    table = models.CharField(_("list"), max_length=60)
    columns = models.JSONField(_("columns"), default=list)
    #: UIX-050 (UIX-012): the entries per page chosen last, 5 to 1,000; empty: the default.
    page_size = models.PositiveSmallIntegerField(_("entries per page"), null=True, blank=True)
    updated_at = models.DateTimeField(_("changed"), auto_now=True)

    class Meta:
        verbose_name = _("column choice")
        verbose_name_plural = _("column choices")
        constraints = [models.UniqueConstraint(fields=["user", "table"], name="table_preference_unique")]

    def __str__(self) -> str:
        return f"{self.user} – {self.table}"

    @classmethod
    def columns_of(cls, user: Any, table: str) -> list[str] | None:
        """The saved column keys of a user for a list, or ``None`` if nothing was saved.

        Read once per request and kept: a list page asks for it while
        building the table and again for the column chooser.
        """
        cache = _request_cache.get()
        key = ("table_preference", user.pk, table)
        if cache is not None and key in cache:
            return cache[key]
        columns = cls.objects.filter(user=user, table=table).values_list("columns", flat=True).first()
        result = list(columns) if isinstance(columns, list) else None
        if cache is not None:
            cache[key] = result
        return result

    @classmethod
    def save_columns(cls, user: Any, table: str, columns: list[str] | None) -> None:
        """Remember a choice; ``None`` forgets it, so the defaults apply again (a page size stays, UIX-050)."""
        if columns is None:
            rows = cls.objects.filter(user=user, table=table)
            rows.filter(page_size__isnull=True).delete()
            rows.update(columns=[])
        else:
            cls.objects.update_or_create(user=user, table=table, defaults={"columns": columns})
        cache = _request_cache.get()
        if cache is not None:
            cache.pop(("table_preference", user.pk, table), None)

    @classmethod
    def page_size_of(cls, user: Any, table: str) -> int | None:
        """UIX-050: the entries per page a user chose last for a list, or ``None``."""
        return cls.objects.filter(user=user, table=table[:60]).values_list("page_size", flat=True).first()

    @classmethod
    def save_page_size(cls, user: Any, table: str, page_size: int) -> None:
        """UIX-050: remember the entries per page of a list; its columns stay."""
        cls.objects.update_or_create(user=user, table=table[:60], defaults={"page_size": page_size})


class JobStatus(models.TextChoices):
    """Where a task in the background stands (NFA-041)."""

    QUEUED = "queued", _("waiting")
    RUNNING = "running", _("running")
    DONE = "done", _("ready")
    FAILED = "failed", _("failed")


def job_file_path(instance: BackgroundJob, filename: str) -> str:
    """Results of background tasks: one folder per task, under a random name."""
    from pathlib import Path

    extension = Path(filename).suffix.lower()[:10]
    return f"jobs/{instance.pk}/{secrets.token_hex(12)}{extension}"


class BackgroundJob(models.Model):
    """A task that takes long and runs in the background: a large import, many labels, a full export (NFA-041).

    It is started as a process of its own right away (``core.jobs``); the
    timer that runs every minute picks up what was not started, e.g. after
    a restart. Whoever started it is told when it is done and can download
    the result.
    """

    kind = models.CharField(_("kind"), max_length=30)
    title = models.CharField(_("task"), max_length=200)
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=JobStatus.choices, default=JobStatus.QUEUED)
    progress = models.PositiveSmallIntegerField(_("progress"), default=0)
    message = models.TextField(_("message"), blank=True)
    result_file = models.FileField(upload_to=job_file_path, blank=True, max_length=200)
    result_name = models.CharField(max_length=200, blank=True)
    #: What the task found, as data – e.g. the report of an import (IMP-003).
    result = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="background_jobs"
    )
    created_at = models.DateTimeField(_("started"), default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(_("finished"), null=True, blank=True)

    class Meta:
        verbose_name = _("background task")
        verbose_name_plural = _("background tasks")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_finished(self) -> bool:
        """Whether the task is done or failed."""
        return self.status in {JobStatus.DONE, JobStatus.FAILED}


class AccessKind(models.TextChoices):
    """What kind of record an entry of the access log names (AUT-028)."""

    CUSTOMER = "customer", _("customer")
    PERSON = "person", _("person")
    PROJECT = "project", _("project")
    MAIL = "mail", _("project mail")
    ATTACHMENT = "attachment", _("mail attachment")
    PROJECT_FILE = "project_file", _("project file")
    DOCUMENT = "document", _("document")
    LIST = "list", _("list")
    FULL_EXPORT = "full_export", _("full export")
    BACKUP = "backup", _("backup")


class AccessAction(models.TextChoices):
    """How a record was read (AUT-028)."""

    VIEW = "view", _("opened")
    DOWNLOAD = "download", _("downloaded")
    EXPORT = "export", _("exported")
    API = "api", _("read through the API")


class AccessLogEntry(models.Model):
    """One read of personal or business data: who, when, from where, what (AUT-028).

    The change log (:class:`AuditLogEntry`) says who *changed* something; this
    log says who *looked at* it – for the data-protection control. Entries are
    written by :mod:`rentalars.core.access_log` and never edited, except that
    the label of an anonymised customer or person is replaced.

    ``object_id`` is the key of the record, or the name of the list for a CSV
    export. A mail, an attachment, a file or a document names its project as
    ``parent``, so that the filter by project finds them too.
    """

    timestamp = models.DateTimeField(_("time"), default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    user_label = models.CharField(_("user name"), max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    action = models.CharField(_("access"), max_length=10, choices=AccessAction.choices)
    object_type = models.CharField(_("kind of object"), max_length=20, choices=AccessKind.choices)
    object_id = models.CharField(_("object ID"), max_length=60, blank=True)
    label = models.CharField(_("object"), max_length=200, blank=True)
    parent_type = models.CharField(max_length=20, choices=AccessKind.choices, blank=True)
    parent_id = models.CharField(max_length=40, blank=True)
    path = models.CharField(_("page address"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("access log entry")
        verbose_name_plural = _("access log")
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="access_object_idx"),
            models.Index(fields=["parent_type", "parent_id"], name="access_parent_idx"),
            models.Index(fields=["user", "timestamp"], name="access_user_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user_label} {self.action} {self.object_type} {self.object_id}"


# --- UIX-034: where an address lies on the map --------------------------------------------------


class PositionSource(models.TextChoices):
    """How the position of an address came about (UIX-034)."""

    FOUND = "found", _("found by OpenStreetMap")
    NOT_FOUND = "not_found", _("not found")
    MANUAL = "manual", _("set by hand")


class AddressPosition(models.Model):
    """The position of one address on the map, asked once and kept (UIX-034, ``core.maps``).

    The row belongs to the address text, not to a record: venues, customers,
    suppliers, the company and free-text places of projects with the same
    address share it, and a changed address simply has another row. The
    server asks the geocoder (Nominatim) only for addresses without a row; a
    position set by hand replaces what was found. Rows no address uses any
    more are removed by the daily maintenance; those of an anonymised
    customer at once (KND-010).

    Not an ``AuditedModel``: filling the cache is no change of business data.
    A position set by hand is logged as an event of the record whose map it
    was set on.
    """

    #: SHA-256 of the normalised address, see ``core.maps.address_key``.
    key = models.CharField(max_length=64, unique=True)
    address = models.CharField(_("address"), max_length=500)
    latitude = models.DecimalField(_("latitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(_("longitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    source = models.CharField(_("source"), max_length=10, choices=PositionSource.choices)
    #: What the geocoder called the place it found, to compare with the address.
    found_name = models.CharField(_("found as"), max_length=300, blank=True)
    updated_at = models.DateTimeField(_("changed"), default=timezone.now)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("changed by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("position of an address")
        verbose_name_plural = _("positions of addresses")

    def __str__(self) -> str:
        return self.address

    @property
    def is_known(self) -> bool:
        """Whether the address has a place on the map."""
        return self.latitude is not None and self.longitude is not None


# --- PER-009, PER-040: surcharges for night, Sunday and holiday work -----------------------


def _percent_field(label: Any, default: str) -> models.DecimalField:
    """A percentage of the surcharges (PER-009); 0 is no surcharge."""
    return models.DecimalField(
        label,
        max_digits=5,
        decimal_places=2,
        default=Decimal(default),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("500"))],
    )


class TimeSurchargeSettings(SingletonModel):
    """Surcharges for night, Sunday and holiday work on crew lines billed by the hour (PER-009, PER-040).

    Einstellungen → Zuschläge. The surcharges are a list of rules
    (:class:`TimeSurchargeRule`) that works in any country, with the holidays
    of a German federal state and/or own holidays (:class:`OwnHoliday`); the
    button "Nach § 3b EStG einstellen" sets the rules of the law
    (``core.surcharge_presets``). The calculation is
    ``projects.time_surcharges``.

    ``on_price`` and ``on_costs`` say whether a crew line planned from now on
    gets the surcharges – the line keeps its own switches
    (``CrewLine.time_surcharges_on_price``/``…_on_cost``), so that switching
    here never changes a line planned before. Rules and holidays hold for
    every line with surcharges at once.

    ``rules_set_up``: whether the list of rules was made – a new installation
    gets the rules of § 3b EStG on first use (``core.surcharges``);
    an empty list after that means no surcharges.
    """

    on_price = models.BooleanField(
        _("surcharges on the price for the customer"),
        default=False,
        help_text=_(
            "Crew lines planned from now on get them, if billed by the hour; each line can be changed. "
            "Lines planned before stay as they are."
        ),
    )
    on_costs = models.BooleanField(
        _("surcharges on the personnel costs"),
        default=False,
        help_text=_(
            "Crew lines planned from now on get them, if billed by the hour; each line can be changed. "
            "Lines planned before stay as they are."
        ),
    )
    german_holidays = models.BooleanField(
        _("statutory holidays of Germany"),
        default=True,
        help_text=_("Off: only the own holidays count – for work in another country."),
    )
    state = models.CharField(
        _("public holidays of"),
        max_length=3,
        blank=True,
        default="",
        choices=STATE_CHOICES,
        help_text=_("The holidays of the federal state where the work is done; the same for every project."),
    )
    next_day_until = models.TimeField(
        _("for work begun before midnight, a day with a surcharge reaches into the next day until"),
        null=True,
        blank=True,
        default=datetime.time(4, 0),
        help_text=_(
            "Sundays, holidays and other days of the rules count until this time of the next day if the work "
            "began before midnight – § 3b EStG: 4:00. Empty: they end at midnight."
        ),
    )
    rules_set_up = models.BooleanField(default=False, editable=False)

    audit_exclude = frozenset({"rules_set_up"})
    #: AUT-019: the earlier percentages that were turned into rules – their entries in the change
    #: log stay readable only with the price right or the right for personnel costs.
    audit_sensitive = {
        **{
            f"price_{kind}": "prices" for kind in ("night", "night_after_midnight", "sunday", "holiday", "high_holiday")
        },
        **{
            f"cost_{kind}": "personnel_costs"
            for kind in ("night", "night_after_midnight", "sunday", "holiday", "high_holiday")
        },
    }

    class Meta:
        verbose_name = _("surcharges for night, Sunday and holidays")
        verbose_name_plural = _("surcharges for night, Sunday and holidays")

    def __str__(self) -> str:
        return str(_("Surcharges for night, Sunday and holidays"))

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save; the first time, make the rules of § 3b EStG – the defaults (PER-040)."""
        super().save(*args, **kwargs)
        if not self.rules_set_up:
            from rentalars.core.surcharges import install_section_3b

            install_section_3b(self)


class TimeSurchargeRuleKind(models.TextChoices):
    """When a surcharge rule applies (PER-040)."""

    TIME = "time", _("at a time of day")
    WEEKDAY = "weekday", _("on weekdays")
    HOLIDAY = "holiday", _("on public holidays")
    DATE = "date", _("on a day of the year")


#: ISO weekdays (1 Monday … 7 Sunday) and their short names, for :attr:`TimeSurchargeRule.weekdays`.
WEEKDAY_CHOICES = [
    ("1", _("Mon")),
    ("2", _("Tue")),
    ("3", _("Wed")),
    ("4", _("Thu")),
    ("5", _("Fri")),
    ("6", _("Sat")),
    ("7", _("Sun")),
]


def _audit_parent_of_surcharges() -> models.Model:
    """The settings row as the parent in the change log – without a query: it always has the key 1."""
    return TimeSurchargeSettings(pk=1)


class TimeSurchargeRule(AuditedModel):
    """One rule of the surcharges for night, Sunday and holidays (PER-040, PER-009).

    Kinds (:class:`TimeSurchargeRuleKind`):

    * ``time`` – a window of the time of day, ``time_from`` to ``time_until``,
      over midnight if it ends earlier than it begins (20:00–06:00);
      ``begun_before_midnight``: only for work begun before midnight, and then
      instead of the other time-of-day rules (§ 3b (3) Nr. 1 EStG: 40 % from 0
      to 4 o'clock instead of 25 %).
    * ``weekday`` – the ISO weekdays in ``weekdays`` ("67": Saturday and
      Sunday), from ``time_from`` if set.
    * ``holiday`` – the public holidays of the settings, from ``time_from`` if set.
    * ``date`` – a day of the year (``day``.``month``), from ``time_from`` if
      set (24.12. from 14:00).

    How they add up – § 3b EStG stated generally: of the rules of the "day"
    kinds (weekday, holiday, date) only the highest percentage counts; of the
    time-of-day rules too; the two add up. Rules with the same name and
    percentage are one kind of surcharge in the planning and the documents.
    ``code``: the kind of a rule set by "Nach § 3b EStG einstellen"
    (``core.surcharge_presets``), else empty.
    """

    position = models.PositiveIntegerField(_("order"), default=0)
    name = models.CharField(
        _("name"),
        max_length=80,
        help_text=_("Shown in the planning and in documents; rules with the same name and rate count as one."),
    )
    kind = models.CharField(
        _("applies"), max_length=10, choices=TimeSurchargeRuleKind.choices, default=TimeSurchargeRuleKind.TIME
    )
    time_from = models.TimeField(_("from"), null=True, blank=True)
    time_until = models.TimeField(_("until"), null=True, blank=True)
    weekdays = models.CharField(_("weekdays"), max_length=7, blank=True, default="")
    day = models.PositiveSmallIntegerField(
        _("day"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    month = models.PositiveSmallIntegerField(
        _("month"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    begun_before_midnight = models.BooleanField(
        _("only for work begun before midnight"),
        default=False,
        help_text=_("Then it takes the place of the other time-of-day rules, as the 40 percent from 0:00 to 4:00."),
    )
    price_percent = _percent_field(_("on the price, in percent"), "0")
    cost_percent = _percent_field(_("on the costs, in percent"), "0")
    code = models.CharField(max_length=30, blank=True, default="", editable=False)

    #: AUT-019: the percentage of the price with the price right, that of the costs with the personnel cost right.
    audit_sensitive = {"price_percent": "prices", "cost_percent": "personnel_costs"}

    class Meta:
        ordering = ["position", "id"]
        verbose_name = _("surcharge rule")
        verbose_name_plural = _("surcharge rules")

    def __str__(self) -> str:
        return self.name

    def audit_parent(self) -> models.Model | None:
        """The rules show in the history of the settings."""
        return _audit_parent_of_surcharges()

    def clean(self) -> None:
        """Each kind needs its values; the values of the other kinds are emptied (PER-040)."""
        super().clean()
        errors: dict[str, Any] = {}
        kind = self.kind
        if kind == TimeSurchargeRuleKind.TIME:
            if self.time_from is None:
                errors["time_from"] = _("Give the time the rule begins.")
            if self.time_until is None:
                errors["time_until"] = _("Give the time the rule ends.")
            elif self.time_from is not None and self.time_from == self.time_until:
                errors["time_until"] = _("The rule must end at another time than it begins.")
        else:
            self.time_until, self.begun_before_midnight = None, False
        if kind == TimeSurchargeRuleKind.WEEKDAY:
            days = sorted(set(self.weekdays or ""))
            if not days or any(day not in "1234567" for day in days):
                errors["weekdays"] = _("Choose at least one weekday.")
            self.weekdays = "".join(days)
        else:
            self.weekdays = ""
        if kind == TimeSurchargeRuleKind.DATE:
            if self.day is None or self.month is None:
                errors["day"] = _("Give day and month.")
            else:
                try:
                    datetime.date(2000, self.month, self.day)  # a leap year: 29 February is a day of the year
                except ValueError:
                    errors["day"] = _("This day does not exist.")
        else:
            self.day = self.month = None
        if errors:
            raise ValidationError(errors)


class OwnHolidayKind(models.TextChoices):
    """When an own holiday falls (PER-040)."""

    YEARLY = "yearly", _("every year on")
    ONCE = "once", _("once on")
    EASTER = "easter", _("days from Easter Sunday")


class OwnHoliday(AuditedModel):
    """A holiday of the company's own, besides or instead of the statutory ones of Germany (PER-040).

    A day every year (``day``.``month``), one single ``date``, or
    ``easter_offset`` days from Easter Sunday (Easter Monday: 1, Ascension:
    39, Corpus Christi: 60) – so that the surcharges work in any country.
    """

    name = models.CharField(_("name"), max_length=80)
    kind = models.CharField(_("when"), max_length=10, choices=OwnHolidayKind.choices, default=OwnHolidayKind.YEARLY)
    day = models.PositiveSmallIntegerField(
        _("day"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    month = models.PositiveSmallIntegerField(
        _("month"), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    date = models.DateField(_("date"), null=True, blank=True)
    easter_offset = models.SmallIntegerField(
        _("days from Easter Sunday"),
        null=True,
        blank=True,
        validators=[MinValueValidator(-80), MaxValueValidator(240)],
        help_text=_("Easter Monday 1, Ascension 39, Whit Monday 50, Corpus Christi 60; before Easter negative."),
    )

    class Meta:
        ordering = ["id"]
        verbose_name = _("own holiday")
        verbose_name_plural = _("own holidays")

    def __str__(self) -> str:
        return self.name

    def audit_parent(self) -> models.Model | None:
        """The own holidays show in the history of the settings."""
        return _audit_parent_of_surcharges()

    def spec(self) -> OwnHolidaySpec:
        """The holiday for the calendar (``core.holidays.calendar_of``)."""
        return OwnHolidaySpec(
            name=self.name,
            kind=self.kind,
            month=self.month,
            day=self.day,
            date=self.date,
            offset=self.easter_offset,
        )

    def clean(self) -> None:
        """Each kind needs its value; the values of the other kinds are emptied (PER-040)."""
        super().clean()
        errors: dict[str, Any] = {}
        if self.kind == OwnHolidayKind.YEARLY:
            if self.day is None or self.month is None:
                errors["day"] = _("Give day and month.")
            else:
                try:
                    datetime.date(2000, self.month, self.day)
                except ValueError:
                    errors["day"] = _("This day does not exist.")
        else:
            self.day = self.month = None
        if self.kind == OwnHolidayKind.ONCE:
            if self.date is None:
                errors["date"] = _("Give the date.")
        else:
            self.date = None
        if self.kind == OwnHolidayKind.EASTER:
            if self.easter_offset is None:
                errors["easter_offset"] = _("Give the number of days.")
        else:
            self.easter_offset = None
        if errors:
            raise ValidationError(errors)


# ADM-016: a prepared change of the server address, in a module of its own; imported here so that Django finds it.
from rentalars.core.address_models import AddressChange, AddressChangeStatus, CertificateKind  # noqa: E402, F401

# VFG-036: when and how far ahead shortages are reported – Einstellungen → Benachrichtigungen.
from rentalars.core.notification_settings import NotificationSettings, ShortageInterval  # noqa: E402, F401
