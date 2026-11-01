# SPDX-License-Identifier: GPL-3.0-or-later
"""Time entries and expenses (chapter 5.9).

A time entry says that a person worked on a project in a job function from
a start to an end, minus a break (ZEI-002, ZEI-004). An
:class:`Expense` says that a person spent money for a project – meals, a
trip, a night, parking (ZEI-019); it goes through the same statuses.

The life of an entry (ZEI-012)::

    recorded ──submit──▶ submitted ──approve──▶ approved   (locked)
        ▲                    │
        └────── edit ◀── rejected ◀──reject──┘

*recorded*
    written down but not yet handed in: a running stopwatch, or an entry the
    person wants to check again.
*submitted*
    handed in for approval. Still editable by the person.
*approved*
    checked by project management or personnel planning (ZEI-013). Locked
    for everybody; only approved hours count for billing "by effort" and
    for the comparison of planned and actual hours (PRJ-026, PRJ-061).
*rejected*
    sent back with a reason. Editing it and submitting again starts anew.

The hourly rate is copied into the entry when it is created (ZEI-008) and
never follows later changes of the person's rate.
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
from django.utils.translation import pgettext_lazy

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.i18n import local_pattern
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects.models import CrewLine, Project


class TimeEntryStatus(models.TextChoices):
    """The four statuses of a time entry (ZEI-012)."""

    RECORDED = "recorded", _("recorded")
    SUBMITTED = "submitted", _("submitted")
    APPROVED = "approved", _("approved")
    REJECTED = "rejected", _("rejected")


#: Statuses in which the person may still change or delete the entry.
EDITABLE_STATUSES = frozenset(
    {TimeEntryStatus.RECORDED.value, TimeEntryStatus.SUBMITTED.value, TimeEntryStatus.REJECTED.value}
)

#: The longest a single entry may last. Catches a stopwatch forgotten over the
#: weekend and a mistyped date; a real shift with breaks stays far below.
MAX_ENTRY_LENGTH = datetime.timedelta(hours=24)


def elapsed(start: datetime.datetime, end: datetime.datetime) -> datetime.timedelta:
    """The time that really passes between two moments (L2): not their wall-clock difference."""
    if start.tzinfo is not None and end.tzinfo is not None:
        start, end = start.astimezone(datetime.UTC), end.astimezone(datetime.UTC)
    return end - start


def hours_between(start: datetime.datetime, end: datetime.datetime, break_minutes: int = 0) -> Decimal:
    """Return the working hours from start to end minus the break, as a decimal with two places.

    Example: 08:00 to 16:30 with 30 minutes of break is ``8.00`` hours;
    22:00 to 02:15 the next day is ``4.25`` (ZEI-009: over midnight).

    L2: the time that really passes. Two moments of the same time zone
    are subtracted as wall-clock times by Python, so a night across the change
    of the clock was an hour too long or too short; hence both are converted to
    UTC first.
    """
    seconds = elapsed(start, end).total_seconds() - break_minutes * 60
    return (Decimal(max(int(seconds), 0)) / Decimal(3600)).quantize(Decimal("0.01"))


class TimeEntry(AuditedModel):
    """Hours a person worked on a project in a job function (ZEI-002, ZEI-004).

    ``project`` may be empty: a time can be written down before anybody knows
    which project it belongs to (ZEI-023). Such an entry counts nowhere and
    cannot be approved until a project is assigned.

    ``end`` is empty while the stopwatch of the entry is running (ZEI-005).
    ``hours`` is the worked time, kept as a number so that sums over many
    entries are one database query; it is recalculated on every save.

    ``crew_line`` links the entry to the crew line of the same person and job
    function in the project, where there is one (ZEI-021). Entries without
    such a line are listed in the project and can be assigned by hand.
    """

    person = models.ForeignKey(Person, verbose_name=_("person"), on_delete=models.PROTECT, related_name="time_entries")
    project = models.ForeignKey(
        Project,
        verbose_name=_("project"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="time_entries",
    )
    job_function = models.ForeignKey(
        JobFunction, verbose_name=_("job function"), on_delete=models.PROTECT, related_name="time_entries"
    )
    crew_line = models.ForeignKey(
        CrewLine,
        verbose_name=_("crew line"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    start = models.DateTimeField(_("start"))
    end = models.DateTimeField(_("end"), null=True, blank=True)
    break_minutes = models.PositiveSmallIntegerField(
        _("break in minutes"), default=0, validators=[MinValueValidator(0), MaxValueValidator(600)]
    )
    hours = models.DecimalField(_("hours"), max_digits=6, decimal_places=2, default=Decimal("0"), editable=False)
    note = models.CharField(_("note"), max_length=250, blank=True)
    hourly_rate = models.DecimalField(
        _("hourly rate"), max_digits=8, decimal_places=2, default=Decimal("0"), editable=False
    )
    status = models.CharField(
        _("status"), max_length=10, choices=TimeEntryStatus.choices, default=TimeEntryStatus.RECORDED
    )
    submitted_at = models.DateTimeField(_("submitted"), null=True, blank=True, editable=False)
    decided_at = models.DateTimeField(_("decided"), null=True, blank=True, editable=False)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("decided by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    rejection_reason = models.CharField(_("reason for rejection"), max_length=250, blank=True)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    #: ZEI-025: the parts of one period of time worked in several job functions share this key.
    #: Each part is an entry of its own with the period's begin, end, break and note, its own job function,
    #: crew line, rate – and its share of the hours in ``hours``. Empty for an entry that is not split.
    period_key = models.UUIDField(_("period"), null=True, blank=True, editable=False, db_index=True)

    audit_sensitive = {"hourly_rate": SpecialRight.PERSONNEL_COSTS}
    #: ZEI-025: the key is technical; the change log shows the hours and job function of each part instead.
    audit_exclude = frozenset({"period_key"})

    class Meta:
        verbose_name = _("time entry")
        verbose_name_plural = _("time entries")
        ordering = ["-start", "-id"]
        indexes = [
            models.Index(fields=["person", "start", "end"], name="time_person_period_idx"),
            models.Index(fields=["project", "status"], name="time_project_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.person} {self.start:{local_pattern('%d.%m.%Y %H:%M')}} ({self.hours} h)"

    def audit_parent(self) -> models.Model | None:
        """Show changes of an entry in the history of its person (ZEI-014)."""
        return self.person

    # --- State ----------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the stopwatch of this entry is still running (ZEI-005)."""
        return self.end is None

    @property
    def is_locked(self) -> bool:
        """Approved entries are locked (ZEI-012)."""
        return self.status == TimeEntryStatus.APPROVED

    @property
    def is_editable(self) -> bool:
        """Whether the entry may still be changed or deleted."""
        return self.status in EDITABLE_STATUSES

    @property
    def has_project(self) -> bool:
        """Whether a project is assigned; without one the entry cannot be approved (ZEI-023)."""
        return self.project_id is not None

    @property
    def project_label(self) -> str:
        """The project as shown in lists, or a note that there is none yet (ZEI-023)."""
        return str(self.project) if self.project_id else str(_("without project"))

    @property
    def amount(self) -> Decimal:
        """Hours × the hourly rate fixed on the entry: the internal cost of the entry."""
        return (self.hours * self.hourly_rate).quantize(Decimal("0.01"))

    @property
    def is_part(self) -> bool:
        """ZEI-025: whether the entry is one part of a period worked in several job functions."""
        return self.period_key is not None

    @property
    def period_hours(self) -> Decimal:
        """ZEI-025: the hours of the whole period – begin to end minus the break; for a part more than ``hours``."""
        return hours_between(self.start, self.end, self.break_minutes) if self.end else Decimal("0")

    # --- Validation -----------------------------------------------------------

    def clean(self) -> None:
        """Check start, end and break of the entry itself (ZEI-009).

        Whether it overlaps with *other* entries of the person is checked in
        ``timetracking.services``, inside the transaction that saves it.
        """
        super().clean()
        errors: dict[str, Any] = {}
        if self.start and self.end:
            if self.end <= self.start:
                errors["end"] = _("The end must be after the start.")
            elif elapsed(self.start, self.end) > MAX_ENTRY_LENGTH:
                errors["end"] = _("An entry cannot be longer than 24 hours. Check the date.")
            elif self.break_minutes * 60 >= elapsed(self.start, self.end).total_seconds():
                errors["break_minutes"] = _("The break is as long as the whole entry.")
        if self.crew_line_id and self.crew_line.project_id != self.project_id:
            errors["crew_line"] = _("The crew line belongs to a different project.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Keep ``hours`` in step with start, end and break.

        ZEI-025: a part of a period keeps the share of the hours it was given
        (``timetracking.services`` divides the period and keeps the shares adding up).
        """
        if self.end is None:
            self.hours = Decimal("0")
        elif self.period_key is None or not self.hours:
            self.hours = hours_between(self.start, self.end, self.break_minutes)
        super().save(*args, **kwargs)


# --- Expenses and travel costs (ZEI-019) ---------------------------------------------------------------


class ExpenseKind(models.TextChoices):
    """What an expense was for (ZEI-019)."""

    MEALS = "meals", _("Meals")
    #: With kilometres: the own car, kilometres × the rate of the settings; without: a ticket.
    TRAVEL = "travel", pgettext_lazy("expense kind", "Travel")
    LODGING = "lodging", _("Accommodation")
    PARKING = "parking", _("Parking and tolls")
    OTHER = "other", _("Other")


#: The highest amount one expense may have; a typo of a few zeros is caught.
MAX_EXPENSE_AMOUNT = Decimal("99999.99")

#: The most kilometres one trip may have.
MAX_KILOMETRES = Decimal("20000")


def receipt_path(instance: Expense, filename: str) -> str:
    """Store receipts in a folder per person, under a random name (NFA-007)."""
    import secrets
    from pathlib import Path

    extension = Path(filename).suffix.lower()[:10]
    return f"receipts/{instance.person_id}/{secrets.token_hex(12)}{extension}"


class Expense(AuditedModel):
    """Money a person spent for a project: meals, a trip, a night, parking (ZEI-019).

    Entered by the person – on the phone, with a photo of the receipt – or by
    the office, for a project. It goes through the statuses of a time entry
    (:class:`TimeEntryStatus`, ZEI-012): only approved expenses count as
    costs of the project (PRJ-025). Once paid out, the office marks it as
    reimbursed (``reimbursed_on``); a reimbursed expense is locked.

    A trip with the own car is entered as kilometres; ``km_rate`` is copied
    from the settings when the trip is recorded – like the hourly rate of a
    time entry (ZEI-008) – and ``amount`` is kilometres × rate. A trip
    without kilometres (a train ticket) has its amount typed in.
    """

    person = models.ForeignKey(Person, verbose_name=_("person"), on_delete=models.PROTECT, related_name="expenses")
    project = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.PROTECT, related_name="expenses")
    kind = models.CharField(_("kind"), max_length=10, choices=ExpenseKind.choices, default=ExpenseKind.MEALS)
    date = models.DateField(_("date"))
    kilometres = models.DecimalField(
        _("kilometres"),
        max_digits=7,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.1")), MaxValueValidator(MAX_KILOMETRES)],
    )
    km_rate = models.DecimalField(
        _("rate per kilometre"), max_digits=5, decimal_places=2, null=True, blank=True, editable=False
    )
    # ZEI-027: the kilometres of the way to work deducted from this trip; empty: none (older trips).
    commute_km = models.DecimalField(
        _("way to work deducted (km)"), max_digits=7, decimal_places=1, null=True, blank=True, editable=False
    )
    # 0 is allowed for a trip whose kilometres the way to work takes up entirely (ZEI-027); ``clean``
    # asks for at least 0.01 everywhere else.
    amount = models.DecimalField(
        _("amount"),
        max_digits=9,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(MAX_EXPENSE_AMOUNT)],
    )
    note = models.CharField(_("note"), max_length=250, blank=True)
    receipt = models.FileField(_("receipt"), upload_to=receipt_path, blank=True, max_length=200)
    status = models.CharField(
        _("status"), max_length=10, choices=TimeEntryStatus.choices, default=TimeEntryStatus.RECORDED
    )
    submitted_at = models.DateTimeField(_("submitted"), null=True, blank=True, editable=False)
    decided_at = models.DateTimeField(_("decided"), null=True, blank=True, editable=False)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("decided by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    rejection_reason = models.CharField(_("reason for rejection"), max_length=250, blank=True)
    reimbursed_on = models.DateField(_("reimbursed on"), null=True, blank=True, editable=False)
    reimbursed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("reimbursed by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("expense")
        verbose_name_plural = _("expenses")
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["person", "date"], name="expense_person_date_idx"),
            models.Index(fields=["project", "status"], name="expense_project_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.person} {self.date:{local_pattern('%d.%m.%Y')}} {self.get_kind_display()} {self.amount}"

    def audit_parent(self) -> models.Model | None:
        """Show changes of an expense in the history of its person, like time entries (ZEI-014)."""
        return self.person

    @property
    def is_editable(self) -> bool:
        """Whether the expense may still be changed or deleted: not approved (ZEI-012)."""
        return self.status in EDITABLE_STATUSES

    @property
    def is_reimbursed(self) -> bool:
        """Whether the money was paid out to the person."""
        return self.reimbursed_on is not None

    @property
    def is_by_kilometre(self) -> bool:
        """Whether the amount is kilometres × the rate per kilometre."""
        return self.kind == ExpenseKind.TRAVEL and self.kilometres is not None

    @property
    def status_label(self) -> str:
        """The status as shown in lists: "reimbursed" once paid out, else the status (ZEI-019)."""
        return str(_("reimbursed")) if self.is_reimbursed else str(self.get_status_display())

    @property
    def status_key(self) -> str:
        """The status for the colour of its badge; "reimbursed" (neutral grey) once paid out."""
        return "reimbursed" if self.is_reimbursed else self.status

    def apply_kind(self) -> None:
        """Kilometres and their rate only for a trip; a trip by kilometre costs kilometres × rate.

        Called before validation, so that the amount of such a trip is
        there when the fields are checked.
        """
        if self.kind != ExpenseKind.TRAVEL:
            self.kilometres = None
            self.km_rate = None
        elif self.kilometres is None:
            self.km_rate = None
        elif self.km_rate is not None:
            self.amount = (self.billable_kilometres * self.km_rate).quantize(Decimal("0.01"))
        if not self.is_by_kilometre:
            self.commute_km = None

    @property
    def billable_kilometres(self) -> Decimal:
        """The kilometres paid for: those of the trip less the way to work deducted from it (ZEI-027)."""
        if self.kilometres is None:
            return Decimal("0")
        return max(self.kilometres - (self.commute_km or Decimal("0")), Decimal("0"))

    @property
    def distance_label(self) -> str:
        """The kilometres as the lists show them: "42 km", or "42 km − 28 km way to work = 14 km" (ZEI-027)."""
        from rentalars.core.money import format_decimal

        if self.kilometres is None:
            return ""
        kilometres = format_decimal(self.kilometres, max_places=1)
        if not self.commute_km:
            return f"{kilometres} km"
        return _("%(kilometres)s km − %(commute)s km way to work = %(billable)s km") % {
            "kilometres": kilometres,
            "commute": format_decimal(self.commute_km, max_places=1),
            "billable": format_decimal(self.billable_kilometres, max_places=1),
        }

    def clean(self) -> None:
        """Kilometres only for a trip; a trip by kilometre needs its rate; the amount is there.

        The amount is at least 0.01 – except for a trip by kilometre that the way to work takes up
        entirely (ZEI-027): it stays recorded with 0, and the calculation shows why.
        """
        super().clean()
        self.apply_kind()
        if self.kind == ExpenseKind.TRAVEL and self.kilometres is not None and self.km_rate is None:
            raise ValidationError({"kilometres": _("The rate per kilometre is missing.")})
        if self.amount is None:
            raise ValidationError({"amount": _("Enter the amount.")})
        if not (self.is_by_kilometre and self.commute_km):
            try:
                MinValueValidator(Decimal("0.01"))(self.amount)
            except ValidationError as error:
                raise ValidationError({"amount": error.messages}) from error
        self.note = (self.note or "").strip()
