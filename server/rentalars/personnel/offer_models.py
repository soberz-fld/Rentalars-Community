# SPDX-License-Identifier: GPL-3.0-or-later
"""Price offers of freelancers for a deployment request (PER-038).

A freelancer asked for a deployment (PER-016) can answer with a price of their own instead of
confirming the stored rate: an offer per hour, per day or in total, with an optional message and
an optional day until which it holds. The company accepts it, rejects it or counters; the
freelancer answers a counter the same way. The exchange is a short log (:class:`PriceOffer`, one
row per proposal) with a limit of rounds. An accepted offer sets the cost rate of exactly this
crew line (``personnel.offers``); the line then carries a marker.

The feature is optional and off unless the company switches it on (:class:`OfferSettings`,
Einstellungen → Preisangebote). Amounts are personnel costs: they are visible only to the person
who made them and to users with the right "see hourly rates and personnel costs" (AUT-019).

Imported at the end of ``personnel/models.py`` so that Django finds the models.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.models import SingletonModel

#: The only currency offers are made in: the costs of the whole application are in euros.
CURRENCY = "EUR"
#: The largest amount an offer may name (the field holds 10 digits with 2 decimals).
MAX_AMOUNT = Decimal("99999999.99")
#: How many proposals a negotiation may have at most, whatever the settings say.
MAX_ROUNDS_LIMIT = 10
DEFAULT_ROUNDS = 4
#: How many offers one user may make or answer within an hour (a protection against a runaway client).
MAX_ACTIONS_PER_HOUR = 30


class OfferUnit(models.TextChoices):
    """What the amount of an offer is for (PER-038)."""

    HOUR = "hour", _("per hour")
    DAY = "day", _("per day")
    TOTAL = "total", _("in total")


class OfferSide(models.TextChoices):
    """Who made a proposal."""

    FREELANCER = "freelancer", _("freelancer")
    COMPANY = "company", _("company")


class OfferStatus(models.TextChoices):
    """Where a proposal stands (PER-038)."""

    OPEN = "open", _("open")
    ACCEPTED = "accepted", _("accepted")
    REJECTED = "rejected", _("rejected")
    COUNTERED = "countered", _("countered")
    WITHDRAWN = "withdrawn", _("withdrawn")
    #: Overtaken: the request was answered another way, sent again, or the line changed hands.
    LAPSED = "lapsed", _("lapsed")


class ReleaseReason(models.TextChoices):
    """Why an accepted offer no longer sets the cost rate of its line."""

    NONE = "", _("still applies")
    MANUAL = "manual", _("cost rate changed by hand")
    PERSON = "person", _("another person or job function")
    TIMES = "times", _("new times")
    REVOKED = "revoked", _("taken back")


class OfferSettings(SingletonModel):
    """Einstellungen → Preisangebote: whether freelancers may offer their own price, and within which limits (PER-038).

    Off by default: a request is then answered with "accept" or "decline" as before. ``min_percent``
    and ``max_percent`` bound an offer relative to the rate stored for the person (the hourly or day
    rate of the line; for a total the cost the line has now); empty means no limit on that side.
    ``max_rounds`` is the number of proposals – of both sides together – a negotiation about one
    request may have.
    """

    enabled = models.BooleanField(
        _("freelancers may offer their own price"),
        default=False,
        help_text=_("Off: a deployment request is answered with “accept” or “decline” only."),
    )
    also_temporary = models.BooleanField(
        _("temporary staff too"),
        default=False,
        help_text=_("Off: only people of the kind “freelancer” may make an offer."),
    )
    min_percent = models.DecimalField(
        _("lowest offer in percent of the stored rate"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1000"))],
        help_text=_("Empty: no lower limit."),
    )
    max_percent = models.DecimalField(
        _("highest offer in percent of the stored rate"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1000"))],
        help_text=_("Empty: no upper limit. Without a stored rate no limit can be checked."),
    )
    max_rounds = models.PositiveSmallIntegerField(
        _("proposals per request, at most"),
        default=DEFAULT_ROUNDS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_ROUNDS_LIMIT)],
        help_text=_("Offers and counter-offers together; after the last one only accepting or rejecting is left."),
    )

    class Meta:
        verbose_name = _("settings for price offers")
        verbose_name_plural = _("settings for price offers")

    def __str__(self) -> str:
        return str(_("Settings for price offers"))

    def clean(self) -> None:
        """The lowest limit must not exceed the highest."""
        super().clean()
        if self.min_percent is not None and self.max_percent is not None and self.min_percent > self.max_percent:
            raise ValidationError({"max_percent": _("The highest offer must not be lower than the lowest offer.")})


class PriceOffer(AuditedModel):
    """One proposal in the negotiation about the price of a deployment (PER-038).

    The freelancer's offer is round 1; the company's counter round 2 and so on – ``round`` counts the
    proposals of both sides. Only the newest one can be ``open``. Accepting a proposal sets the cost
    rate of the crew line (``applied``); the values the line had before are kept here, so that the
    offer can be taken back (``personnel.offers.release_offer``).

    Everything here is personnel cost (AUT-019): the amounts, the message and the values of the line
    before. The change log shows these only to users with the right; it belongs to the history of the
    person, not to that of the project, so that the project's readers do not see that a price was
    negotiated.
    """

    line = models.ForeignKey(
        "projects.CrewLine", verbose_name=_("crew line"), on_delete=models.CASCADE, related_name="price_offers"
    )
    person = models.ForeignKey(
        "personnel.Person", verbose_name=_("person"), on_delete=models.CASCADE, related_name="price_offers"
    )
    round = models.PositiveSmallIntegerField(_("round"), default=1)
    side = models.CharField(_("made by"), max_length=10, choices=OfferSide.choices)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("entered by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(MAX_AMOUNT)],
    )
    unit = models.CharField(_("for"), max_length=5, choices=OfferUnit.choices, default=OfferUnit.HOUR)
    currency = models.CharField(_("currency"), max_length=3, default=CURRENCY)
    message = models.CharField(_("message"), max_length=500, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=OfferStatus.choices, default=OfferStatus.OPEN)
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True, editable=False)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("decided by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    decision_note = models.CharField(_("reason"), max_length=250, blank=True)
    #: The stored rate for this unit when the proposal was made – to compare with; ``None`` without one.
    reference_amount = models.DecimalField(
        _("stored rate at that time"), max_digits=10, decimal_places=2, null=True, blank=True, editable=False
    )
    #: The request the proposal belongs to (``CrewLine.requested_at``): a new request starts a new negotiation.
    requested_at = models.DateTimeField(null=True, blank=True, editable=False)

    # --- What an accepted offer did to the line (PER-038) ---------------------------------------------------
    applied = models.BooleanField(_("sets the cost rate of the line"), default=False, editable=False)
    release_reason = models.CharField(
        _("no longer applies because"), max_length=10, choices=ReleaseReason.choices, blank=True, editable=False
    )
    previous_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    previous_daily_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    previous_cost_flat_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, editable=False
    )
    previous_hourly_rate_above_limit = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, editable=False
    )
    created_at = models.DateTimeField(_("made at"), default=timezone.now, editable=False)

    audit_sensitive = {
        "amount": SpecialRight.PERSONNEL_COSTS,
        "message": SpecialRight.PERSONNEL_COSTS,
        "decision_note": SpecialRight.PERSONNEL_COSTS,
        "reference_amount": SpecialRight.PERSONNEL_COSTS,
        "previous_hourly_rate": SpecialRight.PERSONNEL_COSTS,
        "previous_daily_rate": SpecialRight.PERSONNEL_COSTS,
        "previous_cost_flat_rate": SpecialRight.PERSONNEL_COSTS,
        "previous_hourly_rate_above_limit": SpecialRight.PERSONNEL_COSTS,
    }

    class Meta:
        verbose_name = _("price offer")
        verbose_name_plural = _("price offers")
        ordering = ["line_id", "requested_at", "round", "id"]
        constraints = [models.UniqueConstraint(fields=["line", "requested_at", "round"], name="price_offer_round_once")]
        indexes = [models.Index(fields=["status", "created_at"], name="price_offer_status_idx")]

    def __str__(self) -> str:
        return f"{self.person} – {self.amount} {self.get_unit_display()}"

    def audit_parent(self) -> models.Model | None:
        """Show offers in the history of the person, not of the project (they are personnel costs)."""
        return self.person

    @property
    def is_open(self) -> bool:
        """Whether the proposal still waits for an answer (and has not run out)."""
        return self.status == OfferStatus.OPEN and not self.has_run_out

    @property
    def has_run_out(self) -> bool:
        """Whether the day until which the proposal held is past (the day itself still counts)."""
        return self.valid_until is not None and self.valid_until < timezone.localdate()

    @property
    def shown_status(self) -> str:
        """The status as people see it: an open proposal that has run out is "expired"."""
        if self.status == OfferStatus.OPEN and self.has_run_out:
            return "expired"
        return str(self.status)

    def clean(self) -> None:
        """Currency and unit; the day until which it holds must not lie in the past when it is made."""
        super().clean()
        if self.currency != CURRENCY:
            raise ValidationError({"currency": _("Offers can only be made in euros (EUR).")})
        if self._state.adding and self.valid_until is not None and self.valid_until < timezone.localdate():
            raise ValidationError({"valid_until": _("The day until which the offer holds must not be in the past.")})
