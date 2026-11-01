# SPDX-License-Identifier: GPL-3.0-or-later
"""Projects, groups, material lines and crew lines (chapter 5.6).

A project bundles a customer, a period, the material planned for it and the
people who work on it. The material is listed as *material lines* (product +
quantity + period), which can be arranged in named *groups* with their own
subtotals. The people are listed as *crew lines* (job function + person +
period), which stand in a block of their own and are never put into groups
(PRJ-038).

Who may see a project is decided per project where a role says so:
``ProjectMembership`` assigns a user to a project, see ``projects.access``
(AUT-016 ff.).

Subprojects and nested groups:

* Subprojects (``Project.parent``, PRJ-031, PRJ-044 ff.): one level of
  parts of a whole project – the stages of a festival, say. Each part has
  its own period, lines, crew and status; customer and billing come from
  the whole project. Material can go straight from one part to the next
  (``MaterialLine.taken_over_from``, PRJ-060). See ``projects.family``.
* Nested groups (``Group.parent``, PRJ-037; see ``projects.grouptree``).
"""

from __future__ import annotations

import datetime
import math
from decimal import Decimal
from functools import cached_property
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext, pgettext_lazy

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.i18n import local_pattern, plural_of
from rentalars.core.money import decimal_separator
from rentalars.customers.models import Contact, Customer
from rentalars.masterdata.models import RentalScaleVersion, Supplier, TaxRate, Unit
from rentalars.products.models import BillingMode, Product, ProductKind


class ProjectStatus(models.TextChoices):
    """The eight statuses a project passes through (PRJ-008)."""

    INQUIRY = "inquiry", _("Inquiry")
    OPTION = "option", _("Option")
    CONFIRMED_OPEN = "confirmed_open", _("Confirmed – details open")
    CONFIRMED = "confirmed", _("Confirmed")
    OUT = "out", _("Out")
    # PRJ-093: in German "Wieder im Lager" – "Zurück" was mistaken for the back button.
    RETURNED = "returned", _("Returned")
    CLOSED = "closed", _("Closed")
    CANCELLED = "cancelled", _("Cancelled")


class InvoiceMark(models.TextChoices):
    """DOK-015: what a project says about its invoice besides the invoices made in Rentalars.

    With invoices made in Rentalars (DOK-014 on) a project is invoiced once it
    has a valid invoice; with invoices written in another program it is
    invoiced once somebody ticks "Rechnung gestellt". Either way a project
    that is never invoiced – free of charge, billed with another one – can be
    marked "no invoice", and the reminders stop.
    """

    OPEN = "", _("open")
    ISSUED = "issued", _("invoice issued")
    NOT_NEEDED = "not_needed", _("no invoice")
    #: Set by the update on every project closed before: its invoice is not followed – nobody knows
    #: whether it was written elsewhere. Reopening the project ends it.
    EARLIER = "earlier", _("closed earlier")


class ProjectKind(models.TextChoices):
    """PRJ-090: a project, or a service case ("Servicefall") – see ``projects.service_cases``."""

    PROJECT = "project", _("project")
    SERVICE_CASE = "service_case", _("service case")


class CaseStatus(models.TextChoices):
    """The statuses of a service case (PRJ-090); projects leave the field empty.

    PRJ-112 adds three statuses that each come with a follow-up
    (``projects.service_cases.FOLLOW_UP_STATUSES``): *waiting* (for a reply,
    an action or a delivery – ``Project.case_waiting_for``), *waiting to
    close* (closed at the day and time of the follow-up unless something
    happens before, ADM-013 default rules) and *backlog* (kept off the
    dashboards until its follow-up is due).
    """

    OPEN = "open", pgettext_lazy("service case", "Open")
    IN_PROGRESS = "in_progress", pgettext_lazy("service case", "In progress")
    WAITING = "waiting", pgettext_lazy("service case", "Waiting")
    CLOSING = "closing", pgettext_lazy("service case", "Waiting to close")
    BACKLOG = "backlog", pgettext_lazy("service case", "Backlog")
    DONE = "done", pgettext_lazy("service case", "Done")


class CaseWaitingFor(models.TextChoices):
    """PRJ-112: what a service case in the status "waiting" waits for."""

    REPLY = "reply", pgettext_lazy("service case waits for", "A reply")
    ACTION = "action", pgettext_lazy("service case waits for", "An action")
    DELIVERY = "delivery", pgettext_lazy("service case waits for", "A delivery of material")


#: PRJ-112: the status "waiting" as shown, with what the case waits for.
CASE_WAITING_LABELS = {
    CaseWaitingFor.REPLY: pgettext_lazy("service case", "Waiting for a reply"),
    CaseWaitingFor.ACTION: pgettext_lazy("service case", "Waiting for an action"),
    CaseWaitingFor.DELIVERY: pgettext_lazy("service case", "Waiting for a delivery"),
}


#: PRJ-008: in these statuses the material of a project is firmly reserved.
FIRM_STATUSES = frozenset({ProjectStatus.CONFIRMED_OPEN.value, ProjectStatus.CONFIRMED.value, ProjectStatus.OUT.value})

#: L10: the groups of statuses are defined here and nowhere else – a new status or a new name is
#: entered once. ``FIRM_STATUSES`` – the material is reserved and the project goes ahead; ``ORDER_STATUSES`` –
#: confirmed, and everything after it, the crew is planned for good and the project counts as an order (PRJ-115,
#: VFG-027); ``EARNING_STATUSES`` – the material went out and earned money (MAT-053); ``UNSETTLED_STATUSES`` –
#: not fully confirmed: changed products are pointed out and can be taken over (PRJ-072).
ORDER_STATUSES = FIRM_STATUSES | frozenset({ProjectStatus.RETURNED.value, ProjectStatus.CLOSED.value})
EARNING_STATUSES = frozenset({ProjectStatus.OUT.value, ProjectStatus.RETURNED.value, ProjectStatus.CLOSED.value})
UNSETTLED_STATUSES = frozenset(
    {ProjectStatus.INQUIRY.value, ProjectStatus.OPTION.value, ProjectStatus.CONFIRMED_OPEN.value}
)

#: PRJ-008: an option reserves "softly" – visible to others, but not binding.
SOFT_STATUSES = frozenset({ProjectStatus.OPTION.value})

#: Statuses in which planning is over; availability is no longer evaluated.
FINISHED_STATUSES = frozenset({ProjectStatus.RETURNED.value, ProjectStatus.CLOSED.value, ProjectStatus.CANCELLED.value})

#: PRJ-045: what a subproject always has from its whole project; not changeable on the subproject.
INHERITED_FIELDS = ("customer", "is_internal", "billing_address")

#: Which status may follow which. Read as "from → allowed targets".
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ProjectStatus.INQUIRY: frozenset(
        {ProjectStatus.OPTION, ProjectStatus.CONFIRMED_OPEN, ProjectStatus.CONFIRMED, ProjectStatus.CANCELLED}
    ),
    ProjectStatus.OPTION: frozenset(
        {ProjectStatus.INQUIRY, ProjectStatus.CONFIRMED_OPEN, ProjectStatus.CONFIRMED, ProjectStatus.CANCELLED}
    ),
    ProjectStatus.CONFIRMED_OPEN: frozenset(
        {ProjectStatus.OPTION, ProjectStatus.CONFIRMED, ProjectStatus.OUT, ProjectStatus.CANCELLED}
    ),
    ProjectStatus.CONFIRMED: frozenset(
        {ProjectStatus.OPTION, ProjectStatus.CONFIRMED_OPEN, ProjectStatus.OUT, ProjectStatus.CANCELLED}
    ),
    ProjectStatus.OUT: frozenset({ProjectStatus.RETURNED, ProjectStatus.CONFIRMED}),
    ProjectStatus.RETURNED: frozenset({ProjectStatus.CLOSED, ProjectStatus.OUT}),
    ProjectStatus.CLOSED: frozenset({ProjectStatus.RETURNED}),
    ProjectStatus.CANCELLED: frozenset({ProjectStatus.INQUIRY}),
}


def _wall_clock(moment: datetime.datetime) -> datetime.datetime:
    """The time on the wall in the local zone, without a zone; a value without zone already is."""
    return moment if timezone.is_naive(moment) else timezone.localtime(moment).replace(tzinfo=None)


def started_days(begin: datetime.datetime | None, finish: datetime.datetime | None) -> int:
    """Count the rental days of a period: every started 24 hours count as one day (PRJ-005).

    Examples: Saturday 18:00 to Sunday 02:00 (8 hours) is 1 day; Friday 10:00
    to Sunday 18:00 (56 hours) is 3 days. A missing or reversed period counts
    as 1 day, so that a half-filled form never leads to a price of zero.

    The hours are those of the clock: Saturday 10:00 to Sunday 10:00 is 1 day
    also across the change of the clocks.
    """
    if not begin or not finish or finish <= begin:
        return 1
    # On the wall clock, not in elapsed time: Saturday 10:00 to Sunday 10:00 is one day also on the night the clocks
    # go back (25 hours). Two aware datetimes of one time zone subtract as wall-clock times, but two of different
    # zones (a value from the database is UTC, one from a form is local) as elapsed time – so both go to local time
    # first and lose their zone, which makes preview and stored value equal.
    local_begin = _wall_clock(begin)
    local_finish = _wall_clock(finish)
    return max(1, math.ceil((local_finish - local_begin) / datetime.timedelta(hours=24)))


def _plain_number(value: Decimal | int) -> str:
    """A quantity without needless decimals, for messages: ``6`` instead of ``6.00``."""
    value = Decimal(value)
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f").replace(".", decimal_separator())  # UIX-029


def suggested_hours(begin: datetime.datetime | None, finish: datetime.datetime | None) -> Decimal:
    """Suggest the planned hours of a crew line from its period (PRJ-023, PRJ-073).

    The hours are always the length of the period – end minus
    start, rounded to quarter hours –, whatever its length: the period is
    taken as worked through. The planner enters fewer hours where the
    nights are free. (Formerly a period of more than 16 hours was read
    as so many working days of its clock times – "Monday 08:00 to Tuesday
    20:00" gave 2 × 12 = 24 hours –, which the users found wrong.)

    The length is the time that really passes: a night across the change to
    summer time is an hour shorter.

    Examples: 08:00 to 14:00 gives 6.00; 08:00 to 09:10 gives 1.25; Monday
    08:00 to Tuesday 20:00 gives 36.00; Friday 10:00 to Sunday 18:00 gives
    56.00. A missing or reversed period suggests nothing (0).
    """
    if not begin or not finish or finish <= begin:
        return Decimal("0")
    # In UTC: two moments of the same time zone would otherwise be subtracted as wall-clock times.
    length = finish.astimezone(datetime.UTC) - begin.astimezone(datetime.UTC)
    quarters = round(length.total_seconds() / 900)
    return (Decimal(quarters) / 4).quantize(Decimal("0.01"))


def calendar_days(begin: datetime.datetime | None, finish: datetime.datetime | None) -> int:
    """Count the calendar days a period touches, in local time (PER-029).

    The days a crew line billed "per day" is charged for: "Monday 08:00 to
    Tuesday 20:00" touches Monday and Tuesday, 2 days; "Saturday 22:00 to
    Sunday 04:00" touches 2 days as well. An end at midnight does not touch
    the new day: "Monday 08:00 to Tuesday 00:00" is 1 day. A missing or
    reversed period counts as 1 day, like the rental days (PRJ-005).
    """
    if not begin or not finish or finish <= begin:
        return 1
    first = timezone.localtime(begin).date()
    last = timezone.localtime(finish - datetime.timedelta(microseconds=1)).date()
    return max(1, (last - first).days + 1)


class Project(AuditedModel):
    """An event, rental or production for a customer (PRJ-001 to PRJ-005).

    Two periods are kept apart (PRJ-005):

    Reservation period (``start`` – ``end``, date and time, PRJ-004)
        From the moment material leaves the warehouse until it is back. This
        period decides about availability and prefills the material lines.

    Event period (``event_start`` – ``event_end``, optional)
        The event itself. It is only used to *suggest* the rental days that
        are charged; see :attr:`suggested_rental_days`.

    Internal projects (ZEI-010)
        Work that belongs to no customer – tidying the warehouse, repairs,
        the office – is booked on projects marked ``is_internal``. They have
        no customer, and every person who records times may book on them,
        whatever projects the person is assigned to.
    """

    number = models.CharField(_("project number"), max_length=30, unique=True, editable=False)
    # ADM-012, ADM-014: the number the project had before an update renumbered it – the number with "P-"
    # (P-2026-0042 → 2026-0042). It is printed on documents and in
    # the subjects of mails, so addresses, mail tags and searches still find the project by it
    # (rentalars.projects.numbers).
    former_number = models.CharField(
        _("former project number"),
        max_length=30,
        blank=True,
        editable=False,
        db_index=True,
        help_text=_("The number before an update renumbered the project; it still finds the project."),
    )
    name = models.CharField(_("name"), max_length=200)
    customer = models.ForeignKey(
        Customer,
        verbose_name=_("customer"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    is_internal = models.BooleanField(
        _("internal project"),
        default=False,
        help_text=_(
            "For times without a customer: warehouse, workshop, office. Everybody who records times can book on it."
        ),
    )
    contact = models.ForeignKey(
        Contact, verbose_name=_("contact"), null=True, blank=True, on_delete=models.SET_NULL, related_name="projects"
    )
    # KND-005: one of the customer's further addresses instead of the main one.
    billing_address = models.ForeignKey(
        "customers.CustomerAddress",
        verbose_name=_("billing address"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("Empty: the address of the customer."),
    )
    delivery_address = models.ForeignKey(
        "customers.CustomerAddress",
        verbose_name=_("delivery address"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("For the delivery note. Empty: the venue, else the address of the customer."),
    )
    venue = models.CharField(_("venue"), max_length=250, blank=True)
    venue_site = models.ForeignKey(
        "customers.Venue",
        verbose_name=_("venue from the master data"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="projects",
        help_text=_("With address, contact on site and notes."),
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("project manager"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_projects",
    )
    status = models.CharField(_("status"), max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.INQUIRY)
    start = models.DateTimeField(_("material out from"))
    end = models.DateTimeField(_("material back by"))
    event_start = models.DateTimeField(_("event from"), null=True, blank=True)
    event_end = models.DateTimeField(_("event until"), null=True, blank=True)
    rental_days = models.PositiveSmallIntegerField(
        _("rental days"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text=_("Days charged for daily rental. Empty: suggested from the event period."),
    )
    # PRJ-123: one discount on the whole project, in percent or as an amount – never both.
    # Discount target: up to six decimals – the percentage that a target amount leads to must reach the cent.
    overall_discount_percent = models.DecimalField(
        _("overall discount in percent"),
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=_("Taken off the net total of the project, after surcharges."),
    )
    overall_discount_amount = models.DecimalField(
        _("overall discount as amount"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Taken off the net total of the project, after surcharges."),
    )
    notes = models.TextField(_("notes"), blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("part of project"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subprojects",
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    # PRJ-105: the follow-up ("Wiedervorlage") – a day, a note and the user it is for, who is notified on that day;
    # the start page and the list of projects show it. Done or removed clears it (``rentalars.projects.follow_up``).
    follow_up_on = models.DateField(_("follow-up on"), null=True, blank=True, editable=False, db_index=True)
    follow_up_note = models.CharField(_("note on the follow-up"), max_length=250, blank=True, editable=False)
    follow_up_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("follow-up for"),
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="follow_up_projects",
    )
    follow_up_notified_at = models.DateTimeField(_("follow-up notified at"), null=True, blank=True, editable=False)
    # PRJ-109: the time of the reminder ("um 14:30"), optional; without one the day counts, as before.
    follow_up_at = models.TimeField(_("follow-up at"), null=True, blank=True, editable=False)
    # PRJ-090: a service case is a quick kind of project – a fault, a question, a repair – with three
    # statuses of its own and no planning; it keeps the project number, the mail tag and the correspondence of a
    # project and can be turned into one (``rentalars.projects.service_cases``).
    kind = models.CharField(
        _("kind"), max_length=14, choices=ProjectKind.choices, default=ProjectKind.PROJECT, editable=False
    )
    case_status = models.CharField(
        _("status of the service case"), max_length=12, choices=CaseStatus.choices, blank=True, editable=False
    )
    # PRJ-112: with the status "waiting" – a reply, an action or a delivery; empty in every other status.
    case_waiting_for = models.CharField(
        _("waiting for"), max_length=10, choices=CaseWaitingFor.choices, blank=True, editable=False
    )
    case_contact = models.CharField(
        _("reported by"),
        max_length=250,
        blank=True,
        help_text=_("Name, phone or e-mail address of whoever reported it, if not a contact of the customer."),
    )
    # PRJ-113, PRJ-114: when each field last changed – key (the name in the API) → moment, set on every
    # save that changes it (``rentalars.projects.field_changes``); the companion app's "the younger change wins".
    field_changed_at = models.JSONField(_("times of change per field"), default=dict, blank=True, editable=False)
    # ADM-013, MAT-057: the defect report a service case was made of – by an automation or from an inquiry.
    source_defect = models.ForeignKey(
        "material.DefectReport",
        verbose_name=_("made of the defect report"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_cases",
        editable=False,
    )
    # DOK-015: "Rechnung gestellt" ticked by hand – with invoices written in another program – or "no invoice".
    invoice_status = models.CharField(
        _("invoice"), max_length=12, choices=InvoiceMark.choices, blank=True, default=InvoiceMark.OPEN
    )

    # PRJ-113: the times of change are bookkeeping of the changes the log notes anyway.
    audit_exclude = frozenset({"follow_up_notified_at", "field_changed_at"})
    # PRJ-123: the overall discount is a price – the log shows it only to who may see prices (AUT-019).
    audit_sensitive = {
        "overall_discount_percent": SpecialRight.PRICES,
        "overall_discount_amount": SpecialRight.PRICES,
    }

    #: PRJ-113: the tracked fields as last saved, compared with on the next save (``field_changes.stamp``).
    _field_values: dict[str, Any] | None = None

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")
        ordering = ["-start", "-id"]
        indexes = [
            models.Index(fields=["status", "start", "end"], name="project_status_period_idx"),
            # PRJ-090: the list of service cases.
            models.Index(fields=["kind", "case_status"], name="project_kind_case_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.number} {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the project; PRJ-113, PRJ-114: note when each field changed, whatever way it changes."""
        from rentalars.projects import field_changes

        if self.invoice_status == InvoiceMark.EARLIER and not self._state.adding:
            # DOK-015: a project closed earlier and opened again is followed from now on.
            before = field_changes.known_values(self) or {}
            if any(name in before and before[name] != getattr(self, name) for name in ("status", "case_status")):
                self.invoice_status = InvoiceMark.OPEN
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = {*kwargs["update_fields"], "invoice_status"}
        kwargs["update_fields"], noted = field_changes.stamp(self, kwargs.get("update_fields"))
        super().save(*args, **kwargs)
        self._field_values = noted

    def refresh_from_db(self, using: str | None = None, fields: Any = None, **kwargs: Any) -> None:
        """Reload the project; PRJ-113: the fields reloaded are what the next save compares with."""
        from rentalars.projects import field_changes

        before = field_changes.known_values(self)
        super().refresh_from_db(using=using, fields=fields, **kwargs)
        self._field_values = field_changes.after_refresh(self, before, fields)

    def clean(self) -> None:
        """Check the periods and the relations to customer and parent project."""
        super().clean()
        errors: dict[str, Any] = {}
        if self.overall_discount_percent is not None and self.overall_discount_amount is not None:
            errors["overall_discount_amount"] = _("Use only one of: overall discount in percent, as an amount.")
        if self.start and self.end and self.end <= self.start:
            errors["end"] = _("The end must be after the start.")
        if bool(self.event_start) != bool(self.event_end):
            errors["event_end"] = _("Enter both start and end of the event, or neither.")
        elif self.event_start and self.event_end and self.event_end <= self.event_start:
            errors["event_end"] = _("The end of the event must be after its start.")
        if self.customer_id is None and not self.is_internal and not self.is_service_case:
            # PRJ-090: a service case may come from somebody who is no customer (yet).
            errors["customer"] = _("Choose the customer. Only internal projects have none.")
        if self.is_service_case and self.parent_id:
            errors["parent"] = _("A service case cannot be part of a project.")
        if self.contact_id and self.contact.customer_id != self.customer_id:
            errors["contact"] = _("The contact does not belong to this customer.")
        for name in ("billing_address", "delivery_address"):
            address = getattr(self, name)
            if address is not None and address.customer_id != self.customer_id:
                errors[name] = _("The address does not belong to this customer.")
        if self.parent_id:
            if self.pk is not None and self.parent_id == self.pk:
                errors["parent"] = _("A project cannot be part of itself.")
            elif self.parent.parent_id is not None:
                # PRJ-044: exactly one level of subprojects.
                errors["parent"] = _("Subprojects cannot have subprojects of their own.")
            elif self.pk is not None and Project.objects.filter(parent_id=self.pk).exists():
                errors["parent"] = _("A project with subprojects cannot become a subproject itself.")
            else:
                self._clean_as_subproject(errors)
        if errors:
            raise ValidationError(errors)

    def _clean_as_subproject(self, errors: dict[str, Any]) -> None:
        """PRJ-044, PRJ-045: what a subproject takes from its whole project, and where it lies in time.

        * Customer and billing come from the whole project and cannot differ.
        * The rental period lies within that of the whole project: the whole
          project is the frame, the parts are planned inside it.
        """
        parent = self.parent
        if self.customer_id != parent.customer_id or self.is_internal != parent.is_internal:
            errors["customer"] = _("A subproject always has the customer of its whole project.")
        elif self.billing_address_id != parent.billing_address_id:
            errors["billing_address"] = _("A subproject always has the billing address of its whole project.")
        if self.start and self.end and (self.start < parent.start or self.end > parent.end):
            errors["start"] = _(
                "A subproject lies within the rental period of its whole project (%(start)s – %(end)s). "
                "Extend that period first."
            ) % {
                "start": timezone.localtime(parent.start).strftime(local_pattern("%d.%m.%Y %H:%M")),
                "end": timezone.localtime(parent.end).strftime(local_pattern("%d.%m.%Y %H:%M")),
            }

    # --- Subprojects (PRJ-031, PRJ-044 ff.) --------------------------------

    @property
    def is_subproject(self) -> bool:
        """Whether this project is a part of a whole project (PRJ-044)."""
        return self.parent_id is not None

    @property
    def is_service_case(self) -> bool:
        """PRJ-090: whether this is a service case ("Servicefall") rather than a project to plan."""
        return self.kind == ProjectKind.SERVICE_CASE

    @property
    def case_status_label(self) -> str:
        """PRJ-112: the status of a service case as shown – "Waiting for a reply" names what it waits for."""
        if self.case_status == CaseStatus.WAITING and self.case_waiting_for in CaseWaitingFor.values:
            return str(CASE_WAITING_LABELS[self.case_waiting_for])
        return str(self.get_case_status_display())

    @property
    def root_id(self) -> int | None:
        """The ID of the whole project: the parent of a subproject, else the project itself."""
        return self.parent_id or self.pk

    @cached_property
    def has_subprojects(self) -> bool:
        """Whether this project has parts (PRJ-044); asked once per object.

        Free of queries for projects loaded through :func:`with_parts_flag` (``projects.access.project_for``
        does so): the flag then comes with the project itself.
        """
        if self.pk is None or self.parent_id is not None:
            return False
        flag = self.__dict__.get("parts_exist")
        if flag is not None:
            return bool(flag)
        return Project.objects.filter(parent_id=self.pk).exists()

    @property
    def is_in_family(self) -> bool:
        """Whether this project is a part of a whole project, or has parts itself."""
        return self.parent_id is not None or self.has_subprojects

    def family_ids(self) -> list[int]:
        """The whole project and all its subprojects, the whole project first (PRJ-046).

        For a project without subprojects that is just the project itself.
        """
        root = self.root_id
        if root is None:
            return []
        return [root, *Project.objects.filter(parent_id=root).order_by("number", "pk").values_list("pk", flat=True)]

    @property
    def venue_label(self) -> str:
        """Where the project takes place: the venue of the master data, the free text, or both."""
        parts = [str(self.venue_site) if self.venue_site_id else "", self.venue]
        return " – ".join(part for part in parts if part)

    @property
    def billing_address_lines(self) -> list[str]:
        """Where the invoice goes (KND-005): the chosen address, else the customer's own."""
        if self.billing_address_id:
            return self.billing_address.address_lines
        return self.customer.address_lines if self.customer_id else []

    @property
    def delivery_address_lines(self) -> list[str]:
        """Where the material goes (DOK-003): the chosen address, else the venue, else the customer."""
        if self.delivery_address_id:
            return self.delivery_address.address_lines
        if self.venue_site_id:
            return [self.venue_site.name, *self.venue_site.address_lines]
        if self.venue:
            return [self.venue]
        return self.billing_address_lines

    @property
    def open_item_count(self) -> int:
        """How many open items are not done yet (PRJ-059); shown on the tab "Course"."""
        return self.open_items.filter(is_done=False).count() if self.pk else 0

    @property
    def mail_tag(self) -> str:
        """The tag that assigns e-mails to this project, e.g. ``[RL#2026-0042]`` (EML-009, EML-011)."""
        from rentalars.mail.tags import tag_for

        return tag_for(self.number)

    @property
    def customer_name(self) -> str:
        """The name of the customer, or "internal" for an internal project (ZEI-010).

        PRJ-090: a service case without customer names who reported it.
        """
        if not self.customer_id and self.is_service_case:
            return self.case_contact
        return self.customer.name if self.customer_id else str(_("internal"))

    @property
    def is_locked(self) -> bool:
        """Closed projects are protected against changes (PRJ-009)."""
        return self.status == ProjectStatus.CLOSED

    @property
    def follow_up_is_due(self) -> bool:
        """Whether the day of the follow-up has come (PRJ-105) – with a time, that time too (PRJ-109)."""
        if self.follow_up_on is None:
            return False
        today = timezone.localdate()
        if self.follow_up_on != today:
            return self.follow_up_on < today
        return self.follow_up_at is None or self.follow_up_at <= timezone.localtime().time()

    @property
    def reserves_firmly(self) -> bool:
        """Whether the material of this project is firmly reserved (PRJ-008)."""
        return self.status in FIRM_STATUSES

    @property
    def reserves_softly(self) -> bool:
        """Whether the project only earmarks its material (status "option")."""
        return self.status in SOFT_STATUSES

    @property
    def is_finished(self) -> bool:
        """Whether the material is back or the project was cancelled."""
        return self.status in FINISHED_STATUSES

    @property
    def suggested_rental_days(self) -> int:
        """Suggest the rental days from the event period (PRJ-005).

        Every started 24 hours of the event count as one day; without an
        event period the reservation period is used instead.

        Examples: Saturday 18:00 to Sunday 02:00 (8 hours) is 1 day; Friday
        10:00 to Sunday 18:00 (56 hours) is 3 days.
        """
        return started_days(self.event_start or self.start, self.event_end or self.end)

    @property
    def effective_rental_days(self) -> int:
        """The rental days of the project: the entered value or the suggestion."""
        return self.rental_days or self.suggested_rental_days

    @property
    def allowed_next_statuses(self) -> list[str]:
        """The statuses the project may change to from its current one."""
        allowed = ALLOWED_TRANSITIONS.get(self.status, frozenset())
        return [status for status in ProjectStatus.values if status in allowed]


def with_parts_flag(queryset: models.QuerySet[Project]) -> models.QuerySet[Project]:
    """Load projects together with the answer to "has parts?" (``parts_exist``, PRJ-044).

    Every project page asks it for its head (the tab "Subprojects"); this way
    it costs no query of its own.
    """
    return queryset.annotate(parts_exist=models.Exists(Project.objects.filter(parent_id=models.OuterRef("pk"))))


class ProjectAccessLevel(models.TextChoices):
    """The levels of access to a single project (AUT-025).

    "No access" exists for subprojects only: it takes away, in this one
    part, what a membership of the whole project gives (PRJ-049).
    """

    NONE = "none", _("no access")
    DEPLOYMENT = "deployment", _("deployment view")
    READ = "read", _("read")
    EDIT = "edit", _("edit")


class ProjectMembership(AuditedModel):
    """Explicit assignment of a user to a project (AUT-016, AUT-018).

    A membership matters for users whose role covers "assigned projects
    only" (AUT-017): it opens the project for them, up to the level named
    here and never beyond what their role allows. Users whose role covers all
    projects need no membership. See ``projects.access`` for how the two are
    combined.

    Besides explicit memberships there is the automatic one: a person planned
    in a crew line sees the deployment view of that project (AUT-018). That
    needs no row here.

    A membership of a whole project holds in all its subprojects; one of a
    subproject replaces it there, for more or for less – down to "no
    access" (PRJ-049).
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships")
    level = models.CharField(max_length=12, choices=ProjectAccessLevel.choices, default=ProjectAccessLevel.READ)

    class Meta:
        verbose_name = _("project membership")
        verbose_name_plural = _("project memberships")
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="project_membership_unique")]

    def __str__(self) -> str:
        return f"{self.user} @ {self.project}"

    def audit_parent(self) -> models.Model | None:
        """Show who was given access in the history of the project (PRJ-032)."""
        return self.project


class GroupKind(models.TextChoices):
    """Whether a group counts towards the project total (PRJ-040)."""

    NORMAL = "normal", _("normal")
    OPTIONAL = "optional", _("optional")
    ALTERNATIVE = "alternative", _("alternative")


class Group(AuditedModel):
    """A named section of a project's lines with its own subtotal (PRJ-014, PRJ-039).

    A group can carry *one* of three price adjustments: a discount in percent,
    a discount as an amount, or a flat price that replaces the sum of its
    lines.

    Optional and alternative groups are shown with their price but do not
    count towards the project total and do not reserve material firmly
    (PRJ-040).

    Groups can stand inside groups, up to three levels deep (PRJ-037, see
    ``projects.grouptree``). ``position`` counts among the groups with the
    same parent. A subgroup of an optional or alternative group counts as
    optional or alternative too (:attr:`effective_kind`), and a subgroup
    without rental days of its own takes those of the nearest group above
    that has some (:attr:`effective_rental_days`).
    """

    project = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(_("name"), max_length=120)
    description = models.TextField(_("description"), blank=True)
    parent = models.ForeignKey(
        "self", verbose_name=_("parent group"), null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    position = models.PositiveIntegerField(_("position"), default=0)
    kind = models.CharField(_("counts as"), max_length=12, choices=GroupKind.choices, default=GroupKind.NORMAL)
    #: PRJ-083: the group an alternative group could replace. Deleting that group makes this one optional.
    alternative_to = models.ForeignKey(
        "self",
        verbose_name=_("alternative to"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alternatives",
    )
    discount_percent = models.DecimalField(
        _("discount in percent"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    discount_amount = models.DecimalField(
        _("discount as amount"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    flat_price = models.DecimalField(
        _("flat price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Replaces the sum of the lines."),
    )
    rental_days = models.PositiveSmallIntegerField(
        _("rental days"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text=_("Empty: as the project."),
    )

    audit_sensitive = {
        "discount_percent": SpecialRight.PRICES,
        "discount_amount": SpecialRight.PRICES,
        "flat_price": SpecialRight.PRICES,
    }

    class Meta:
        verbose_name = _("group")
        verbose_name_plural = _("groups")
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.name

    def audit_parent(self) -> models.Model | None:
        """Show group changes in the history of the project (PRJ-032)."""
        return self.project

    # --- Nesting (PRJ-037) ----------------------------------------------------
    # These walk up through ``parent``. ``projects.grouptree.GroupTree`` puts
    # the parents into Django's cache, so for groups loaded through it no
    # query is needed; for a single group it is at most two short lookups.

    @property
    def ancestors(self) -> list[Group]:
        """The groups above this one, the nearest first (PRJ-037)."""
        found: list[Group] = []
        current = self.parent if self.parent_id else None
        while current is not None and current is not self and current not in found:
            found.append(current)
            current = current.parent if current.parent_id else None
        return found

    @property
    def depth(self) -> int:
        """0 for a top-level group, 1 for its subgroups, 2 below them (PRJ-037)."""
        return len(self.ancestors)

    @property
    def path(self) -> str:
        """The names from the top down to this group: "Licht › Front-Traverse" (PRJ-037)."""
        from rentalars.projects.grouptree import PATH_SEPARATOR

        return PATH_SEPARATOR.join([*(group.name for group in reversed(self.ancestors)), self.name])

    @property
    def effective_kind(self) -> str:
        """Normal, optional or alternative – as set here, or inherited from a group above (PRJ-037, PRJ-040).

        A subgroup of an optional group is optional too, whatever it says
        itself: the customer takes the option with everything in it, or
        nothing of it. A group's own "optional" or "alternative" wins over
        the kind of the groups above.
        """
        if self.kind != GroupKind.NORMAL:
            return self.kind
        for ancestor in self.ancestors:
            if ancestor.kind != GroupKind.NORMAL:
                return ancestor.kind
        return GroupKind.NORMAL

    @property
    def effective_kind_label(self) -> str:
        """The words for :attr:`effective_kind`: "optional", "alternative" or "normal"."""
        return str(GroupKind(self.effective_kind).label)

    @property
    def kind_is_inherited(self) -> bool:
        """True if the group is optional or alternative only because a group above it is (PRJ-037)."""
        return self.kind == GroupKind.NORMAL and self.effective_kind != GroupKind.NORMAL

    @property
    def effective_rental_days(self) -> int | None:
        """The rental days typed in on this group, or else on the nearest group above (PRJ-037, PRJ-062)."""
        if self.rental_days:
            return self.rental_days
        return next((ancestor.rental_days for ancestor in self.ancestors if ancestor.rental_days), None)

    @property
    def has_price_rule(self) -> bool:
        """Whether the group has a discount or a flat price (PRJ-039)."""
        return any(value is not None for value in (self.discount_percent, self.discount_amount, self.flat_price))

    @property
    def counts_toward_total(self) -> bool:
        """Whether the subtotal of this group is part of the project total (PRJ-040, PRJ-037: also above)."""
        return self.effective_kind == GroupKind.NORMAL

    def clean(self) -> None:
        """PRJ-039: discount in percent, discount as amount or flat price – only one. PRJ-037: a valid place."""
        super().clean()
        adjustments = [
            value for value in (self.discount_percent, self.discount_amount, self.flat_price) if value is not None
        ]
        if len(adjustments) > 1:
            raise ValidationError(_("Use only one of: discount in percent, discount as amount, flat price."))
        if self.parent_id:
            if self.parent.project_id != self.project_id:
                raise ValidationError({"parent": _("The parent group belongs to a different project.")})
            self._check_place_in_tree()
        if self.alternative_to_id:
            self._check_alternative()

    def _check_alternative(self) -> None:
        """PRJ-083: an alternative group names another group of the project that it could replace.

        Not itself, not a group that is an alternative itself, and not a
        group above or below it – the choice is between two sections, not
        between a section and a part of it.
        """
        target = self.alternative_to
        if self.kind != GroupKind.ALTERNATIVE:
            raise ValidationError({"alternative_to": _("Only an alternative names what it could replace.")})
        if target.project_id != self.project_id:
            raise ValidationError({"alternative_to": _("The group belongs to a different project.")})
        if target.pk == self.pk:
            raise ValidationError({"alternative_to": _("A group cannot be an alternative to itself.")})
        if target.kind == GroupKind.ALTERNATIVE:
            raise ValidationError({"alternative_to": _("Choose a group that is not an alternative itself.")})
        links = dict(Group.objects.filter(project_id=self.project_id).values_list("pk", "parent_id"))
        if self.pk is not None:
            links[self.pk] = self.parent_id
        for start, other in ((self.parent_id, target.pk), (links.get(target.pk), self.pk)):
            current, seen = start, set()
            while current is not None and current not in seen:
                if current == other:
                    raise ValidationError(
                        {"alternative_to": _("A group cannot be an alternative to a group above or below it.")}
                    )
                seen.add(current)
                current = links.get(current)

    def _check_place_in_tree(self) -> None:
        """PRJ-037: no group inside itself or its own subgroups, and no more than three levels.

        Reads the parent links of all groups of the project with one query:
        the groups in the database may be in a different place than the
        instances the caller holds.
        """
        from rentalars.projects.grouptree import MAX_DEPTH

        links = dict(Group.objects.filter(project_id=self.project_id).values_list("pk", "parent_id"))
        if self.pk is not None:
            links[self.pk] = self.parent_id
        # Up from the new parent: meeting this group again means a cycle.
        levels_above, current, seen = 0, self.parent_id, set()
        while current is not None and current not in seen:
            if current == self.pk:
                raise ValidationError(
                    {"parent": _("A group cannot be placed inside itself or inside one of its own subgroups.")}
                )
            seen.add(current)
            levels_above += 1
            current = links.get(current)
        # Down from this group: how many levels its subgroups add.
        below, level, frontier = 0, 0, {self.pk} if self.pk is not None else set()
        while frontier and level <= MAX_DEPTH:
            frontier = {pk for pk, parent in links.items() if parent in frontier}
            if frontier:
                level += 1
                below = level
        if levels_above + 1 + below > MAX_DEPTH:
            raise ValidationError(
                {
                    "parent": _("Groups can be nested at most %(levels)d levels deep; this would make %(depth)d.")
                    % {"levels": MAX_DEPTH, "depth": levels_above + 1 + below}
                }
            )


class LineVariant(models.TextChoices):
    """Whether a single line counts towards the project total (PRJ-075).

    The same idea as optional and alternative groups (PRJ-040), for one line:
    "a second follow spot, if you like". Such a line is shown with its price
    but left out of the totals and the invoice, and reserves its material
    only softly, like an option.
    """

    NORMAL = "", _("normal")
    OPTIONAL = "optional", _("optional")
    ALTERNATIVE = "alternative", _("alternative")


class SubrentalStatus(models.TextChoices):
    """Where a subrental stands with the supplier (PRJ-057).

    PRJ-101: "open" comes first and is the default – nothing is asked yet,
    often no supplier is chosen yet. Every other status needs a supplier
    (:meth:`MaterialLine.clean`): "requested" without one made no sense.
    """

    OPEN = "open", _("open")
    REQUESTED = "requested", _("requested")
    ORDERED = "ordered", _("ordered")
    RECEIVED = "received", _("received")
    RETURNED = "returned", pgettext_lazy("subrental status", "returned")


class MaterialLine(AuditedModel):
    """One line of a project: product, quantity and period (PRJ-010).

    Price fields are *copies*. When the line is created, price, unit, tax rate
    and billing mode are taken from the product and then belong to the line;
    later changes to the product do not reach existing lines (PRJ-015).

    Special forms of a line, all stored in this table:

    Free line (PRJ-017)
        ``product`` is empty; ``title``, quantity and price are typed in.

    Subrental (PRJ-018)
        The product is of the kind "subrental". ``supplier`` and
        ``purchase_price`` describe the deal with the supplier. If
        ``covers_line`` is set, the subrental exists only to cover a shortage
        of that line and is not charged to the customer (PRJ-055).

    Surcharge (PRD-031)
        The product is of the kind "surcharge". A percentage surcharge has
        ``surcharge_percent`` set and names what it refers to in
        ``SurchargeTarget`` rows; its amount is calculated, never stored.

    Sale (PRD-013)
        ``is_sale`` marks a line that sells instead of renting.
        ``stock_removed_quantity`` counts how much of it has already been
        taken out of the stock for good.

    A specific model or item (PRJ-064)
        Planning works with products: "6 cables", whichever six. Sometimes
        the planner wants particular material all the same – the mixing desk
        with the newer firmware, the one rack that is already wired.
        ``preferred_model`` and ``preferred_item`` note that wish. It is an
        internal hint for the warehouse: it appears in the planning and on
        the packlist and never on anything the customer sees. Availability
        is still counted per product; a wish that cannot be met shows up as
        a warning (see ``projects.wishes``), it never blocks saving.

    Text line ("Textposition einfügen"; PRJ-128)
        ``is_text`` marks a line that only carries a text – ``title`` and, if
        wanted, a longer ``note`` – like a heading or a remark in a list of
        positions. It has no product, quantity 0, no price and no discount,
        is never optional, never packed, never checked for availability and
        never taken over; it stands in a group like any other line and
        moves, is copied and deleted with it. Documents and the price
        overview print it as a row of text without quantity and amount;
        packlists, the electronic invoice, accounting exports and every
        sum skip it (:meth:`clean`).

    Taken over from another subproject (PRJ-060)
        ``taken_over_from`` names a line of another part of the same whole
        project whose pieces this line takes over: they go straight from one
        stage to the next instead of back to the warehouse. The availability
        counts them as one continuous reservation, the line appears on the
        packlists of both parts, and it is not charged a second time.

    Optional and alternative lines (PRJ-075)
        ``variant`` marks a line the customer may add or choose instead. It
        is priced but not part of the totals or the invoice, and it reserves
        its material softly. See :class:`LineVariant`. An
        alternative names the line it could replace in ``alternative_to``
        (PRJ-083); lines marked "alternative" before may name none.

    The price the line took over (PRJ-072)
        ``list_price`` is the price of the product at the moment the line
        took it over. When the product's price changes later, the line keeps
        its own price (PRJ-015), but the planning of a project that is not
        confirmed yet points it out (see ``projects.price_updates``). A unit
        price that differs from ``list_price`` was set by hand. Lines from
        May not know it (``None``).
    """

    project = models.ForeignKey(
        Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="material_lines"
    )
    group = models.ForeignKey(
        Group, verbose_name=_("group"), null=True, blank=True, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        Product,
        verbose_name=_("product"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_lines",
    )
    title = models.CharField(_("title"), max_length=200)
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.ForeignKey(
        Unit, verbose_name=_("unit"), null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    start = models.DateTimeField(_("from"))
    end = models.DateTimeField(_("until"))
    position = models.PositiveIntegerField(_("position"), default=0)
    note = models.TextField(_("note"), blank=True)

    # --- Price (copied from the product, PRJ-015) ---------------------------
    is_sale = models.BooleanField(_("sale"), default=False)
    billing_mode = models.CharField(
        _("billing mode"), max_length=20, choices=BillingMode.choices, default=BillingMode.FLAT
    )
    unit_price = models.DecimalField(_("unit price"), max_digits=10, decimal_places=2, default=Decimal("0"))
    discount_percent = models.DecimalField(
        _("discount in percent"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    tax_rate = models.ForeignKey(
        TaxRate, verbose_name=_("tax rate"), on_delete=models.PROTECT, related_name="material_lines"
    )
    hours = models.DecimalField(
        _("hours"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("For billing by the hour."),
    )
    quantity_is_estimate = models.BooleanField(
        _("quantity is an estimate"),
        default=False,
        help_text=_("For billing by effort: replace the estimate by the actual effort after the event."),
    )

    # --- Rental days and scale (PRD-035 to PRD-037) -------------------------
    rental_days = models.PositiveSmallIntegerField(
        _("rental days"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text=_("Empty: as the group or the project."),
    )
    scale_version = models.ForeignKey(
        RentalScaleVersion,
        verbose_name=_("rental scale"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_lines",
    )
    manual_scale_factor = models.DecimalField(
        _("scale factor set by hand"),
        max_digits=7,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # --- Surcharge (PRD-031) -------------------------------------------------
    surcharge_percent = models.DecimalField(
        _("surcharge in percent"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1000"))],
    )

    # --- Subrental (PRJ-018, PRJ-054) ---------------------------------------
    supplier = models.ForeignKey(
        Supplier,
        verbose_name=pgettext_lazy("subrental", "supplier"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subrental_lines",
    )
    purchase_price = models.DecimalField(
        _("purchase price per unit"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("What the supplier charges per unit for the whole period."),
    )
    subrental_status = models.CharField(
        _("subrental status"), max_length=12, choices=SubrentalStatus.choices, blank=True
    )
    # PRJ-097: fetched from the supplier and brought back – a trip at packing and at the follow-up work.
    picked_up_at_supplier = models.BooleanField(
        _("picked up at the supplier"),
        default=False,
        help_text=_("Off: the supplier delivers and collects."),
    )
    covers_line = models.ForeignKey(
        "self",
        verbose_name=_("covers shortage of"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="covering_lines",
    )
    covers_product = models.ForeignKey(
        Product, verbose_name=_("covered product"), null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # --- Taken over from another subproject (PRJ-060) ----------------------
    taken_over_from = models.ForeignKey(
        "self",
        verbose_name=_("taken over from"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="taken_over_by",
        help_text=_(
            "The pieces come straight from this line of another subproject, not from the warehouse. "
            "They are charged only once, on that line."
        ),
    )

    # --- A specific model or item (PRJ-064) ---------------------------------
    preferred_model = models.ForeignKey(
        "material.MaterialModel",
        verbose_name=_("specific model"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="preferring_lines",
    )
    preferred_item = models.ForeignKey(
        "material.MaterialItem",
        verbose_name=_("specific item"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="preferring_lines",
    )
    # (piece share; PRJ-064, PRD-052): a line stands for quantity × pieces-per-product items; the planner can
    # name several of them, each one covers one piece. ``preferred_item`` is the first, these are the others.
    further_preferred_items = models.ManyToManyField(
        "material.MaterialItem",
        verbose_name=_("further specific items"),
        blank=True,
        related_name="also_preferring_lines",
    )

    # --- Sale (PRD-013) ------------------------------------------------------
    stock_removed_quantity = models.DecimalField(
        _("already taken out of stock"), max_digits=10, decimal_places=2, default=Decimal("0"), editable=False
    )
    #: PCK-013: added while packing, not in the planning – a "Nachtrag".
    is_addendum = models.BooleanField(_("added while packing"), default=False, editable=False)

    # --- Optional and alternative lines (PRJ-075) ----------------------------
    variant = models.CharField(
        _("counts as"),
        max_length=12,
        choices=LineVariant.choices,
        blank=True,
        default=LineVariant.NORMAL,
        help_text=_("Optional and alternative lines are shown with their price, but not added to the total."),
    )
    #: PRJ-083: the line an alternative line could replace. Deleting that line makes this one optional.
    alternative_to = models.ForeignKey(
        "self",
        verbose_name=_("alternative to"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alternatives",
    )

    # --- A line that only carries text (text line; PRJ-128) ---------------------
    is_text = models.BooleanField(
        _("text line"),
        default=False,
        help_text=_("A line that only carries a text – a heading or a remark. No product, no quantity, no price."),
    )

    # --- The price of the product when the line took it over (PRJ-072) -------
    list_price = models.DecimalField(
        _("price of the product when taken over"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
    )

    # --- What the line took over from its product besides the price (PRJ-072) ---
    product_seen = models.JSONField(
        _("state of the product when taken over"),
        default=dict,
        blank=True,
        editable=False,
        help_text=_(
            "Name, unit, tax rate and billing mode of the product at the moment the line took them over, "
            "so that a later change can be pointed out. A missing entry: not known."
        ),
    )

    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    audit_sensitive = {
        "unit_price": SpecialRight.PRICES,
        "discount_percent": SpecialRight.PRICES,
        "manual_scale_factor": SpecialRight.PRICES,
        "surcharge_percent": SpecialRight.PRICES,
        "purchase_price": SpecialRight.PURCHASE_PRICES,
        "list_price": SpecialRight.PRICES,
    }
    #: Bookkeeping of the line, no change worth a line in the history.
    audit_exclude = frozenset({"product_seen"})

    class Meta:
        verbose_name = _("material line")
        verbose_name_plural = _("material lines")
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["product", "start", "end"], name="line_product_period_idx"),
        ]

    def __str__(self) -> str:
        if self.is_text:
            return self.title
        return f"{self.quantity_display} × {self.title}"

    def audit_parent(self) -> models.Model | None:
        """Show line changes in the history of the project (PRJ-032)."""
        return self.project

    # --- What kind of line is this? ----------------------------------------

    @property
    def kind(self) -> str:
        """The kind of the product, ``"free"`` for a line without product, ``"text"`` for a text line."""
        if self.is_text:
            return "text"
        return self.product.kind if self.product_id else "free"

    @property
    def is_free_line(self) -> bool:
        """A line without product that is priced (PRJ-017); a text line is none."""
        return self.product_id is None and not self.is_text

    @property
    def is_subrental(self) -> bool:
        """A line that plans material from a supplier (PRJ-018)."""
        return self.kind == ProductKind.SUBRENTAL

    @property
    def is_covering_subrental(self) -> bool:
        """A subrental that only covers the shortage of another line (PRJ-055)."""
        return self.covers_line_id is not None

    @property
    def is_takeover(self) -> bool:
        """A line whose pieces come straight from a line of another subproject (PRJ-060)."""
        return self.taken_over_from_id is not None

    @property
    def is_surcharge(self) -> bool:
        """A surcharge line, fixed or percentage (PRD-031)."""
        return self.kind == ProductKind.SURCHARGE

    @property
    def is_percent_surcharge(self) -> bool:
        """A surcharge calculated as a percentage of other amounts."""
        return self.is_surcharge and self.surcharge_percent is not None

    @property
    def uses_rental_days(self) -> bool:
        """Whether rental days and the scale factor enter the price (PRD-033)."""
        return not self.is_sale and self.billing_mode in BillingMode.daily_modes()

    @property
    def counts_toward_total(self) -> bool:
        """Optional and alternative lines are priced, but not added up (PRJ-075)."""
        return not self.variant

    @property
    def is_customer_material(self) -> bool:
        """PRJ-096: the customer's own material, taken along and never charged (``projects.customer_material``)."""
        return self.product_id is not None and self.product.owner_id is not None

    def has_own_period(self, project: Project | None = None) -> bool:
        """Whether the line is out at other times than its project (PRJ-011).

        Args:
            project: The line's project if the caller has it at hand; saves
                loading it once per line.
        """
        project = project or self.project
        return (self.start, self.end) != (project.start, project.end)

    @property
    def days_of_own_period(self) -> int:
        """The rental days that follow from the line's own period (PRJ-062)."""
        return started_days(self.start, self.end)

    @property
    def quantity_display(self) -> str:
        """The quantity without needless decimals: ``6`` instead of ``6.00``."""
        quantity = self.quantity
        if quantity == quantity.to_integral_value():
            return str(int(quantity))
        return format(quantity.normalize(), "f").replace(".", decimal_separator())  # UIX-029

    @property
    def pieces_total(self) -> int:
        """How many items the line stands for: its quantity times the pieces of one product (piece share; PRD-052).

        A line of 2 × "10-pack" stands for 20 items; a line of 6 × a plain cable for 6. 0 for a line without product.
        """
        if not self.product_id or self.is_text:
            return 0
        return max(math.ceil(self.quantity), 1) * self.product.pieces_per_product

    @property
    def wished_items(self) -> list[Any]:
        """All items the line wishes for, the first one first (piece share; PRJ-064).

        ``preferred_item`` and ``further_preferred_items``; with the latter prefetched this costs no query.
        """
        items = [self.preferred_item] if self.preferred_item_id else []
        pending = getattr(self, "pending_further_items", None)
        if pending is not None:
            further = pending  # named by the caller, not saved yet (``services.add_line`` / ``update_line``)
        elif self.pk and self.preferred_item_id:  # further items only go with a first one: no query without a wish
            further = self.further_preferred_items.all()
        else:
            further = []
        items += sorted(
            (item for item in further if item.pk != self.preferred_item_id),
            key=lambda item: item.inventory_number,
        )
        return items

    def copy_further_items_of(self, source: MaterialLine) -> None:
        """Take over the further wished items of ``source`` into this saved copy – no more than it has pieces (R3-8).

        (review.) The copy is checked before the items are stored, so a line whose product has fewer pieces
        than the source had wished items (the number was lowered after the source project was finished) would
        otherwise keep wishes the line cannot hold. The first items in the order of the inventory numbers stay.
        """
        room = max(self.pieces_total - 1, 0) if self.preferred_item_id else 0
        items = sorted(source.further_preferred_items.all(), key=lambda item: item.inventory_number)
        self.further_preferred_items.set(items[:room])

    @property
    def wished_item_ids(self) -> list[int]:
        """The IDs of :attr:`wished_items` – without loading the first item (the planning asks this for every line)."""
        ids = [self.preferred_item_id] if self.preferred_item_id else []
        pending = getattr(self, "pending_further_items", None)
        if pending is not None:
            further = pending
        elif self.pk:
            further = self.further_preferred_items.all()
        else:
            further = []
        ids += (
            [item.pk for item in sorted(further, key=lambda item: item.inventory_number) if item.pk != ids[0]]
            if ids
            else []
        )
        return ids

    # --- Validation ---------------------------------------------------------

    def clean(self) -> None:
        """Check period, quantities and the combination of special fields."""
        super().clean()
        errors: dict[str, Any] = {}
        if self.start and self.end and self.end <= self.start:
            errors["end"] = _("The end must be after the start.")
        if self.group_id and self.project_id and self.group.project_id != self.project_id:
            errors["group"] = _("The group belongs to a different project.")
        if self.product_id:
            needs_whole_pieces = self.product.tracks_stock or self.product.is_kit
            if needs_whole_pieces and self.quantity != self.quantity.to_integral_value():
                errors["quantity"] = _("This product is planned in whole pieces.")
            if self.product.owner_id is not None:
                # PRJ-096: customer material – only in the owner's projects, never charged.
                from rentalars.projects.customer_material import clean_line

                clean_line(self, errors)
            # PRD-047: a line that sold a rental product before (or rented a sale product)
            # keeps its own price and stays valid, also in copies (PRJ-015); a new one is refused when it is
            # created or switched (``services.defaults_from_product``).
            elif self.is_sale and self.product.sale_price is None and self.product.kind != ProductKind.RENTAL:
                errors["is_sale"] = _("This product has no sale price and cannot be sold.")
            elif (
                not self.is_sale
                and self.product.price is None
                and not self.product.is_percent_surcharge
                and self.product.kind != ProductKind.SALE
            ):
                errors["is_sale"] = _("This product has no rental price and can only be sold.")
        if self.is_text:
            self._clean_text(errors)
        self._clean_preference(errors)
        if self.subrental_status not in ("", SubrentalStatus.OPEN) and not self.supplier_id:
            # PRJ-101: asked, ordered, received or back – always with somebody; without a supplier it is "open".
            errors["subrental_status"] = _("Without a supplier the status can only be “open”.")
        if self.covers_line_id:
            if self.pk is not None and self.covers_line_id == self.pk:
                errors["covers_line"] = _("A line cannot cover its own shortage.")
            elif self.covers_line.project_id != self.project_id:
                errors["covers_line"] = _("The covered line belongs to a different project.")
        if self.taken_over_from_id:
            self._clean_takeover(errors)
        if self.alternative_to_id:
            self._clean_alternative(errors)
        if self.pk is not None and "quantity" not in errors:
            taken = self.taken_over_by.exclude(pk=self.pk).aggregate(total=models.Sum("quantity"))["total"] or 0
            if self.quantity < taken:
                errors["quantity"] = ngettext(
                    "%(count)s piece of this line is taken over by other subprojects. Reduce those lines first.",
                    "%(count)s pieces of this line are taken over by other subprojects. Reduce those lines first.",
                    plural_of(taken),
                ) % {"count": _plain_number(taken)}
        if errors:
            raise ValidationError(errors)

    def _clean_text(self, errors: dict[str, Any]) -> None:
        """Text line: a line that only carries text has no product, quantity, price or special form.

        The text is the title; a longer text can stand in the note.
        """
        if not (self.title or "").strip():
            errors["title"] = _("A text line needs a text.")
        if self.product_id:
            errors["product"] = _("A text line has no product.")
        if self.quantity or self.unit_price or self.discount_percent or self.hours or self.surcharge_percent:
            errors["quantity"] = _("A text line has no quantity, price or discount.")
        if self.variant or self.alternative_to_id:
            errors["variant"] = _("A text line is neither optional nor an alternative.")
        if self.covers_line_id or self.taken_over_from_id or self.supplier_id or self.is_sale:
            errors["is_text"] = _("A text line is no subrental, no sale and cannot be taken over.")
        if self.preferred_model_id or self.preferred_item_id:
            errors["preferred_model"] = _("A text line has no specific model or item.")

    def _clean_takeover(self, errors: dict[str, Any]) -> None:
        """PRJ-060: a line can take over the pieces of an earlier line of another part of the same whole project.

        Rules: the same product, not a sale, a line of another project of the
        same whole project that starts earlier; and together with the other
        lines taking over from it, not more pieces than it has.
        """
        source = self.taken_over_from
        project = self.project
        if self.pk is not None and source.pk == self.pk:
            errors["taken_over_from"] = _("A line cannot take over from itself.")
        elif source.project_id == self.project_id:
            errors["taken_over_from"] = _("Material is taken over from another subproject, not from the same one.")
        elif (source.project.parent_id or source.project_id) != (project.parent_id or project.pk):
            errors["taken_over_from"] = _("Material can only be taken over within the same whole project.")
        elif self.product_id is None or source.product_id != self.product_id:
            errors["taken_over_from"] = _("A line can only take over the same product.")
        elif self.is_sale or source.is_sale:
            errors["taken_over_from"] = _("Sold material cannot be taken over.")
        elif self.start and source.start >= self.start:
            errors["taken_over_from"] = _("The line to take over from has to start earlier than this one.")
        else:
            others = source.taken_over_by.all()
            if self.pk is not None:
                others = others.exclude(pk=self.pk)
            left = source.quantity - (others.aggregate(total=models.Sum("quantity"))["total"] or 0)
            if self.quantity > left:
                errors["quantity"] = ngettext(
                    "At most %(count)s piece can still be taken over from that line.",
                    "At most %(count)s pieces can still be taken over from that line.",
                    plural_of(max(left, 0)),
                ) % {"count": _plain_number(max(left, 0))}

    def _clean_alternative(self, errors: dict[str, Any]) -> None:
        """PRJ-083: an alternative names another line of the same project that it could replace.

        Not itself, not a subrental that only covers a shortage (it follows
        its line), and not a line that is an alternative itself.
        """
        target = self.alternative_to
        if self.variant != LineVariant.ALTERNATIVE:
            errors["alternative_to"] = _("Only an alternative names what it could replace.")
        elif target.project_id != self.project_id:
            errors["alternative_to"] = _("The line belongs to a different project.")
        elif self.pk is not None and target.pk == self.pk:
            errors["alternative_to"] = _("A line cannot be an alternative to itself.")
        elif target.is_text:  # (text lines; PRJ-128)
            errors["alternative_to"] = _("A text line has no price and cannot be replaced by an alternative.")
        elif target.covers_line_id is not None:
            errors["alternative_to"] = _("A subrental that covers a shortage cannot be replaced by an alternative.")
        elif target.variant == LineVariant.ALTERNATIVE:
            errors["alternative_to"] = _("Choose a line that is not an alternative itself.")

    def _clean_preference(self, errors: dict[str, Any]) -> None:
        """Check the wish for a specific model or item (PRJ-064).

        * Only products with a stock of their own can carry a wish; a kit or
          a service has no items to choose from.
        * The item must belong to the line's product. Choosing an item also
          fixes the model: it is the item's model.
        * The model must be one whose items (or some of them) belong to the
          line's product.
        """
        if not self.preferred_item_id and not self.preferred_model_id:
            return
        if not self.product_id or not self.product.tracks_stock:
            errors["preferred_model"] = _("Only products with a stock of their own can name a specific model or item.")
            return
        if self.preferred_item_id:
            item = self.preferred_item
            item_product = item.product
            if item_product is None or item_product.pk != self.product_id:
                errors["preferred_item"] = _("The item %(id)s does not belong to the product %(product)s.") % {
                    "id": item.display_id,
                    "product": self.product.article_number,
                }
                return
            self.preferred_model = item.material_model
            self._clean_piece_share(errors)
            return
        model = self.preferred_model
        belongs = (
            model.default_product_id == self.product_id
            or model.items.filter(product_override_id=self.product_id).exists()
        )
        if not belongs:
            errors["preferred_model"] = _("The model %(model)s does not belong to the product %(product)s.") % {
                "model": model.name,
                "product": self.product.article_number,
            }

    def _clean_piece_share(self, errors: dict[str, Any]) -> None:
        """(piece share): no more items wished than the line has pieces – each wished item covers one piece."""
        items = self.wished_items
        for item in items[1:]:
            item_product = item.product
            if item_product is None or item_product.pk != self.product_id:
                errors["preferred_item"] = _("The item %(id)s does not belong to the product %(product)s.") % {
                    "id": item.display_id,
                    "product": self.product.article_number,
                }
                return
        count = len(items)
        total = self.pieces_total
        if count > total:
            errors["preferred_item"] = ngettext(
                "%(count)d item is wished, but the line has only %(total)d piece. Each wished item takes one piece.",
                "%(count)d items are wished, but the line has only %(total)d pieces. Each wished item takes one piece.",
                total,
            ) % {"count": count, "total": total}


class SurchargeTargetType(models.TextChoices):
    """What a percentage surcharge can refer to (PRD-031)."""

    LINE = "line", _("line")
    GROUP = "group", _("group")
    PERSONNEL = "personnel", _("personnel")
    PROJECT = "project", _("whole project")


class SurchargeTarget(models.Model):
    """One thing a percentage surcharge refers to (PRD-031, PRD-039).

    A surcharge line can have several targets, e.g. two groups. The base
    amount of the surcharge is the sum over its targets.
    """

    surcharge_line = models.ForeignKey(MaterialLine, on_delete=models.CASCADE, related_name="surcharge_targets")
    target_type = models.CharField(max_length=10, choices=SurchargeTargetType.choices)
    target_line = models.ForeignKey(MaterialLine, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    target_group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.CASCADE, related_name="+")

    class Meta:
        verbose_name = _("surcharge target")
        verbose_name_plural = _("surcharge targets")
        ordering = ["id"]

    def __str__(self) -> str:
        if self.target_type == SurchargeTargetType.LINE and self.target_line:
            return self.target_line.title
        if self.target_type == SurchargeTargetType.GROUP and self.target_group:
            return self.target_group.name
        return self.get_target_type_display()


class CrewBilling(models.TextChoices):
    """How a crew line is charged to the customer (PRJ-061; "per day", PER-029)."""

    PLAN = "plan", _("by plan")
    FLAT = "flat", _("flat rate")
    EFFORT = "effort", _("by effort")
    DAY = "day", _("per day")


class RequestStatus(models.TextChoices):
    """Where a deployment request stands (PER-016).

    ``FIRM`` (PER-041): planned without asking. It counts like an
    accepted request – in "Meine Einsätze", the calendars and the deployment
    view – and is never asked again by itself: new times are told to the
    person instead (``projects.crew_changes``).
    """

    NONE = "", _("not asked")
    REQUESTED = "requested", _("asked")
    ACCEPTED = "accepted", _("accepted")
    DECLINED = "declined", _("declined")
    FIRM = "firm", _("planned firmly")


class CrewLine(AuditedModel):
    """One person – or one open place – in a job function on a project (PRJ-019).

    Two sides that never mix (PER-008, PRJ-051):

    The price for the customer
        comes from the service product of the job function. ``unit_price`` is
        the price per hour, copied from the product when the line is created
        and from then on the line's own (PRJ-015 applies here too).
        ``billing`` says which hours are charged (PRJ-061):

        ===========  ===================================================
        by plan      planned hours × price per hour
        flat rate    the price itself, whatever the hours (PER-018)
        by effort    approved hours × price per hour; until times are
                     approved the planned hours stand in as an estimate
        per day      days × price per day (PER-029); the days are those
                     typed in (``days``), else the calendar days the
                     period touches
        ===========  ===================================================

        ``discount_percent`` lowers the amount. The job function can set a
        maximum discount that no crew line of it exceeds (PER-026, see
        ``projects.discounts``).

    The cost for the company
        comes from the person. ``hourly_rate`` and ``daily_rate`` are copied
        from the person's rates for the job function when the person is
        assigned (PRJ-021, PER-029), and stay as they are when the person's
        rates change later. A line billed per day costs days × day rate, any
        other line hours × hourly rate. Instead, a flat amount for the whole
        deployment can be agreed (``cost_flat_rate``, PER-018). All of them
        are visible only with the right "see hourly rates and personnel
        costs" (AUT-019).

    A line without person is an open place (PRJ-020): "2 × stagehand,
    Saturday 08–14" are two lines without person, filled later. Until then
    the calculation shows the customer price and, as cost, the guide value of
    the job function (PRJ-052).

    Crew lines belong to the project as a whole and are never put into
    groups (PRJ-038). A line can belong to a phase of its project
    (PRJ-080): the schedule shows per phase who works, and moving the phase
    can move its crew along (``projects.course.update_phase``). Deleting the
    phase keeps the line and its period; only the link goes.
    """

    project = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="crew_lines")
    job_function = models.ForeignKey(
        "personnel.JobFunction", verbose_name=_("job function"), on_delete=models.PROTECT, related_name="crew_lines"
    )
    person = models.ForeignKey(
        "personnel.Person",
        verbose_name=_("person"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="crew_lines",
    )
    start = models.DateTimeField(_("from"))
    end = models.DateTimeField(_("until"))
    planned_hours = models.DecimalField(
        _("planned hours"),
        max_digits=7,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    meeting_point = models.CharField(_("meeting point"), max_length=200, blank=True)
    note = models.TextField(_("note"), blank=True, help_text=_("Visible to the person in the deployment view."))
    position = models.PositiveIntegerField(_("position"), default=0)
    #: PRJ-080: the phase the line belongs to; ``None`` for a line of the whole project.
    phase = models.ForeignKey(
        "ProjectPhase",
        verbose_name=_("phase"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="crew_lines",
    )
    #: PER-029: the days charged "per day"; empty: the calendar days of the period (:attr:`effective_days`).
    days = models.PositiveSmallIntegerField(
        _("days"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text=_("Charged with “per day”. Empty: the calendar days of the period."),
    )

    # --- Price for the customer (PRJ-051, PRJ-061) ---------------------------
    service_product = models.ForeignKey(
        Product,
        verbose_name=_("service product"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="crew_lines",
    )
    title = models.CharField(_("title"), max_length=200)
    billing = models.CharField(_("billing"), max_length=10, choices=CrewBilling.choices, default=CrewBilling.PLAN)
    unit_price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Per hour; with “per day” per day; with “flat rate” the price of the whole deployment."),
    )
    tax_rate = models.ForeignKey(
        TaxRate, verbose_name=_("tax rate"), on_delete=models.PROTECT, related_name="crew_lines"
    )
    #: PER-026: the discount of the line; the job function may limit what is granted.
    discount_percent = models.DecimalField(
        _("discount in percent"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    #: PRJ-072: the price of the service product when the line took it over.
    list_price = models.DecimalField(
        _("price of the product when taken over"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
    )
    #: PER-035: hour tiers per day, copied from the service product – the hours of one day beyond
    #: ``hours_limit`` cost ``unit_price_above_limit`` (and ``hourly_rate_above_limit`` as cost).
    hours_limit = models.DecimalField(
        _("limit in hours per day"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.25")), MaxValueValidator(Decimal("23.75"))],
        help_text=_("The hours of one day beyond this cost the price from the limit. Empty: every hour the same."),
    )
    unit_price_above_limit = models.DecimalField(
        _("price per hour from the limit"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    #: PER-009: surcharges for night, Sunday and holidays on the price – set when the line is planned from
    #: the settings and the service product (``projects.time_surcharges``); off on older lines.
    time_surcharges_on_price = models.BooleanField(
        _("surcharges for night, Sunday and holidays on the price"),
        default=False,
        help_text=_("Only by plan or by effort. The percentages are set under Settings → Surcharges."),
    )

    # --- Cost for the company (PRJ-021, PER-018) -----------------------------
    hourly_rate = models.DecimalField(
        _("hourly rate"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Internal cost per hour, copied from the person when assigned."),
    )
    #: PER-029: the person's own day rate when assigned; a line billed per day costs days × this.
    daily_rate = models.DecimalField(
        _("day rate"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Internal cost per day, copied from the person when assigned; used with “per day”."),
    )
    cost_flat_rate = models.DecimalField(
        _("flat rate for the person"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Internal cost of the whole deployment, instead of hours × hourly rate."),
    )
    #: PER-035: the person's own rate for an hour beyond the limit, copied when the person is assigned.
    hourly_rate_above_limit = models.DecimalField(
        _("hourly rate from the limit"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Internal cost of an hour beyond the limit, copied from the person when assigned."),
    )
    #: PER-009: surcharges for night, Sunday and holidays on the costs, set as ``time_surcharges_on_price``.
    time_surcharges_on_cost = models.BooleanField(
        _("surcharges for night, Sunday and holidays on the costs"),
        default=False,
        help_text=_("Only by plan or by effort, not with a flat rate for the person."),
    )

    # --- LOG-008: who goes with which vehicle, and who drives ---------
    vehicle_line = models.ForeignKey(
        "VehicleLine",
        verbose_name=_("vehicle"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="crew_lines",
        help_text=_("The vehicle of this project the person travels with."),
    )
    is_driver = models.BooleanField(_("driver"), default=False)

    # --- Deployment request (PER-016) -----------------------------------------
    request_status = models.CharField(
        _("request"), max_length=10, choices=RequestStatus.choices, blank=True, default=RequestStatus.NONE
    )
    requested_at = models.DateTimeField(_("asked at"), null=True, blank=True, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("asked by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    answered_at = models.DateTimeField(_("answered at"), null=True, blank=True, editable=False)
    answer_note = models.CharField(_("answer"), max_length=250, blank=True)
    #: PER-033, PER-034: the period the person was last asked for – what an answer refers to.
    requested_start = models.DateTimeField(_("asked for from"), null=True, blank=True, editable=False)
    requested_end = models.DateTimeField(_("asked for until"), null=True, blank=True, editable=False)

    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    audit_sensitive = {
        "unit_price": SpecialRight.PRICES,
        "discount_percent": SpecialRight.PRICES,
        "list_price": SpecialRight.PRICES,
        "hourly_rate": SpecialRight.PERSONNEL_COSTS,
        "daily_rate": SpecialRight.PERSONNEL_COSTS,
        "cost_flat_rate": SpecialRight.PERSONNEL_COSTS,
        "unit_price_above_limit": SpecialRight.PRICES,
        "hourly_rate_above_limit": SpecialRight.PERSONNEL_COSTS,
    }

    class Meta:
        verbose_name = _("crew line")
        verbose_name_plural = _("crew lines")
        ordering = ["start", "position", "id"]
        indexes = [models.Index(fields=["person", "start", "end"], name="crew_person_period_idx")]

    def __str__(self) -> str:
        who = self.person.name if self.person_id else _("not filled yet")
        return f"{self.job_function}: {who}"

    def audit_parent(self) -> models.Model | None:
        """Show crew changes in the history of the project (PRJ-032)."""
        return self.project

    @property
    def is_vacant(self) -> bool:
        """Whether the place still waits for a person (PRJ-020)."""
        return self.person_id is None

    @property
    def period_hours(self) -> Decimal:
        """The hours suggested for the period of this line; see :func:`suggested_hours`."""
        return suggested_hours(self.start, self.end)

    @property
    def period_days(self) -> int:
        """The calendar days the period of this line touches; see :func:`calendar_days` (PER-029)."""
        return calendar_days(self.start, self.end)

    @property
    def effective_days(self) -> int:
        """The days a line billed per day is charged for: typed in, else :attr:`period_days` (PER-029)."""
        return self.days or self.period_days

    @property
    def is_billed_per_day(self) -> bool:
        """Whether the customer pays per day (PER-029)."""
        return self.billing == CrewBilling.DAY

    @property
    def is_confirmed(self) -> bool:
        """Whether the person takes the deployment: accepted, or planned firmly without request (PER-041; PER-016)."""
        return self.person_id is not None and self.request_status in (RequestStatus.ACCEPTED, RequestStatus.FIRM)

    @property
    def times_changed_since_request(self) -> bool:
        """PER-033: the line was asked for, and its period is no longer the one the person was asked for.

        Only start and end count – not the phase, the job function or the
        hours. An older line asked for without a stored period counts
        as changed, so that it can still be asked again. A line planned firmly
        (PER-041) has no request that could be out of date: new times are told
        to the person, not asked.
        """
        if not self.request_status or self.person_id is None or self.request_status == RequestStatus.FIRM:
            return False
        if self.requested_start is None or self.requested_end is None:
            return True
        return (self.start, self.end) != (self.requested_start, self.requested_end)

    def clean(self) -> None:
        """Check the period, the service product and the phase (PRJ-080)."""
        super().clean()
        errors: dict[str, Any] = {}
        if self.start and self.end and self.end <= self.start:
            errors["end"] = _("The end must be after the start.")
        if self.service_product_id and self.service_product.kind != ProductKind.SERVICE:
            errors["service_product"] = _("Choose a service product (category D), not a product with stock.")
        if self.phase_id and self.project_id and self.phase.project_id != self.project_id:
            errors["phase"] = _("Choose a phase of this project.")
        # LOG-008: a vehicle of this project, a motor vehicle – a trailer carries nobody; a driver drives one.
        if self.vehicle_line_id and self.project_id:
            if self.vehicle_line.project_id != self.project_id:
                errors["vehicle_line"] = _("Choose a vehicle booked in this project.")
            elif not self.vehicle_line.is_car:
                errors["vehicle_line"] = _("Nobody travels on a trailer. Choose a motor vehicle.")
        if self.is_driver and not self.vehicle_line_id:
            errors["is_driver"] = _("A driver drives a vehicle: choose it.")
        # PER-035: a limit of hours per day needs its price, and the price its limit.
        if self.hours_limit is not None and self.unit_price_above_limit is None:
            errors["unit_price_above_limit"] = _("Enter the price per hour from the limit.")
        elif self.hours_limit is None and self.unit_price_above_limit is not None:
            errors["hours_limit"] = _("Enter the limit from which the higher price applies.")
        if errors:
            raise ValidationError(errors)

    @property
    def has_hour_tiers(self) -> bool:
        """PER-035: whether the hours of a day beyond a limit cost more – only for lines billed by the hour."""
        return self.hours_limit is not None and self.billing in (CrewBilling.PLAN, CrewBilling.EFFORT)


# --- Phases, open items and files of a project (PRJ-006, PRJ-059, PRJ-007) ---------


class PhaseKind(models.TextChoices):
    """The usual stages of a project (PRJ-006), in the order a project goes through them.

    PRJ-092: "Planungen und Besprechungen" before everything else,
    "Packen" instead of "Verladen" (the stored value stays ``loading``) and
    "Nachbereitung" after the return – unpacking, putting away, checking what
    came back. PRJ-071: the cleaning comes after that; "other" is last.
    """

    PLANNING = "planning", _("Planning and meetings")
    LOADING = "loading", pgettext_lazy("phase", "Packing")
    TRAVEL = "travel", _("Travel")
    SETUP = "setup", _("Setup")
    REHEARSAL = "rehearsal", _("Rehearsal")
    EVENT = "event", _("Event")
    TEARDOWN = "teardown", _("Teardown")
    RETURN = "return", _("Return")
    AFTERCARE = "aftercare", _("Follow-up work")
    CLEANING = "cleaning", _("Cleaning")
    OTHER = "other", _("Other")


class ProjectPhase(AuditedModel):
    """One stage of a project with its own period and place (PRJ-006).

    Phases describe the course of a project for the people who work on it –
    "setup Friday 14–20 in hall 3" – and appear in the calendar and the
    deployment view. They do not change the reservation period of the
    material, which stays the period of the project.

    Crew lines can belong to a phase (``CrewLine.phase``,
    PRJ-080): the page "Zeitplanung" lists per phase who works, and the price
    overview breaks the personnel down by phase and job function (PRJ-088).
    """

    project = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="phases")
    kind = models.CharField(_("phase"), max_length=12, choices=PhaseKind.choices, default=PhaseKind.SETUP)
    title = models.CharField(_("label"), max_length=120, blank=True, help_text=_("Optional, e.g. “Setup hall 3”."))
    start = models.DateTimeField(_("from"))
    end = models.DateTimeField(_("until"))
    venue_site = models.ForeignKey(
        "customers.Venue",
        verbose_name=_("venue from the master data"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="phases",
    )
    location = models.CharField(
        _("place"), max_length=250, blank=True, help_text=_("If not a venue of the master data.")
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("phase")
        verbose_name_plural = _("phases")
        ordering = ["start", "id"]

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """The label, or the name of the kind of phase."""
        return self.title or str(self.get_kind_display())

    @property
    def place(self) -> str:
        """Where the phase takes place, as text."""
        parts = [str(self.venue_site) if self.venue_site_id else "", self.location]
        return " – ".join(part for part in parts if part)

    def audit_parent(self) -> models.Model | None:
        """Show phase changes in the history of the project."""
        return self.project

    def clean(self) -> None:
        """The end must follow the start."""
        super().clean()
        if self.start and self.end and self.end <= self.start:
            raise ValidationError({"end": _("The end must be after the start.")})


class OpenItem(AuditedModel):
    """Something still to be clarified for a confirmed project (PRJ-059).

    Typical for the status "Confirmed – details open": the order is placed,
    but the setup times or the contact on site are missing. Every open item
    is listed in the overview of open items; when the last one is done, the
    project page suggests switching to "Confirmed".
    """

    project = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="open_items")
    text = models.CharField(_("open item"), max_length=250)
    is_done = models.BooleanField(_("done"), default=False)
    done_at = models.DateTimeField(_("done at"), null=True, blank=True, editable=False)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("done by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("open item")
        verbose_name_plural = _("open items")
        ordering = ["is_done", "created_at", "id"]

    def __str__(self) -> str:
        return self.text

    def audit_parent(self) -> models.Model | None:
        """Show open items in the history of the project."""
        return self.project


class SupplierDocumentKind(models.TextChoices):
    """What a document of a supplier of subrentals is (PRJ-106)."""

    OFFER = "offer", _("offer")
    CONFIRMATION = "confirmation", _("order confirmation")
    DELIVERY_NOTE = "delivery", _("delivery note")
    INVOICE = "invoice", _("invoice")
    OTHER = "other", _("other")


def project_file_path(instance: ProjectFile, filename: str) -> str:
    """Store project files in a folder per project, under a random name.

    The original name is kept in the database; on the disk a random name
    avoids clashes and never contains anything a user typed.
    """
    import secrets
    from pathlib import Path

    extension = Path(filename).suffix.lower()[:10]
    return f"projects/{instance.project_id}/{secrets.token_hex(12)}{extension}"


class ProjectFile(AuditedModel):
    """A file of a project: stage plan, rider, contract, order … (PRJ-007).

    Uploaded files follow the rules for uploads (NFA-007): only known
    document types, limited in size, delivered only after the rights were
    checked. Who may see the project sees its files; the crew in the
    deployment view sees only the files marked ``visible_to_crew``.
    """

    project = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="files")
    document_type = models.ForeignKey(
        "masterdata.DocumentType",
        verbose_name=_("document type"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="files",
    )
    title = models.CharField(_("title"), max_length=200, blank=True)
    file = models.FileField(_("file"), upload_to=project_file_path, max_length=200)
    original_name = models.CharField(_("file name"), max_length=255)
    size = models.PositiveBigIntegerField(_("size"), default=0)
    visible_to_crew = models.BooleanField(
        _("visible to the crew"), default=False, help_text=_("Shown in the deployment view of the people planned.")
    )
    source_attachment = models.ForeignKey(
        "mail.MailAttachment",
        verbose_name=_("from e-mail attachment"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_files",
        editable=False,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("uploaded by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    uploaded_at = models.DateTimeField(_("uploaded"), default=timezone.now, editable=False)
    # --- PRJ-106: a document of a supplier of subrentals (offer, confirmation, invoice …) ---------------
    supplier = models.ForeignKey(
        "masterdata.Supplier",
        verbose_name=pgettext_lazy("subrental", "supplier"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_files",
    )
    supplier_document_kind = models.CharField(
        _("kind of document"), max_length=12, choices=SupplierDocumentKind.choices, blank=True
    )
    # --- PRJ-089: a show file of a lighting console, media server or sound system --------------
    show_system = models.CharField(
        _("console or software"), max_length=80, blank=True, help_text=_("e.g. grandMA3, Eos, Resolume Arena, DM7.")
    )
    show_version = models.CharField(
        _("software version"), max_length=40, blank=True, help_text=_("The version the show was saved with.")
    )
    is_current_show = models.BooleanField(
        _("current show"),
        default=False,
        help_text=_("The show file to load; earlier ones of the same console stay as they are."),
    )

    audit_exclude = frozenset({"file", "size"})

    class Meta:
        verbose_name = _("project file")
        verbose_name_plural = _("project files")
        ordering = ["-uploaded_at", "-id"]

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """The title, or the file name."""
        return self.title or self.original_name

    def audit_parent(self) -> models.Model | None:
        """Show file changes in the history of the project."""
        return self.project

    def clean(self) -> None:
        """PRJ-106: the kind of a supplier's document goes with the supplier; a supplier's file has a kind."""
        super().clean()
        if self.supplier_document_kind and not self.supplier_id:
            raise ValidationError({"supplier_document_kind": _("Only a document of a supplier has this kind.")})
        if self.supplier_id and not self.supplier_document_kind:
            self.supplier_document_kind = SupplierDocumentKind.OTHER


class ProjectTemplate(AuditedModel):
    """A project to start from: its groups and lines, crew places and course (PRJ-076).

    Made from a project ("save as template") and used when a new project is
    created. The content is a copy taken at that moment, not a link: later
    changes of the source project do not change the template, and deleting
    the project keeps it. Times are kept relative to the project's start and
    move with the new project (``project_templates.apply_template``).
    Products are referred to by their key; a product that is gone or
    deactivated by then is left out and named.
    """

    name = models.CharField(_("name"), max_length=120, unique=True)
    description = models.TextField(_("description"), blank=True)
    content = models.JSONField(_("content"), default=dict, editable=False)
    source_number = models.CharField(_("made from project"), max_length=30, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    audit_exclude = frozenset({"content"})

    class Meta:
        verbose_name = _("project template")
        verbose_name_plural = _("project templates")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def counts(self) -> dict[str, int]:
        """How many groups, lines, crew places, phases and open items the template holds."""
        return {key: len(self.content.get(key, [])) for key in ("groups", "lines", "crew", "phases", "open_items")}


# --- PRJ-108: people taking part in a service case -----------------------------------------------


class ServiceCaseParticipant(AuditedModel):
    """A person who takes part in a service case ("Beteiligte", PRJ-108).

    Not crew planning: no period, no availability check, no deployment
    request and no costs from the plan. The person sees the case under
    "My area" and is notified when added; the case is among the person's
    own choices when recording times (ZEI-024). With a role for assigned
    projects only, taking part opens the case for reading
    (``projects.access``).

    The change log keeps the person and the job function as IDs.
    """

    project = models.ForeignKey(
        Project, verbose_name=_("service case"), on_delete=models.CASCADE, related_name="participants"
    )
    person = models.ForeignKey(
        "personnel.Person",
        verbose_name=_("person"),
        on_delete=models.CASCADE,
        related_name="service_case_participations",
    )
    job_function = models.ForeignKey(
        "personnel.JobFunction",
        verbose_name=_("job function"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_case_participations",
        help_text=_("Optional – what the person does in the case."),
    )
    note = models.CharField(_("note"), max_length=250, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("added by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("added"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("person taking part")
        verbose_name_plural = _("people taking part")
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "person"], name="service_case_participant_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.person} @ {self.project}"

    def audit_parent(self) -> models.Model | None:
        """Show who takes part in the history of the case (PRJ-032)."""
        return self.project


# --- PRJ-111: trips changed, removed or added by hand ------------------------------------------------


class TripAdjustment(AuditedModel):
    """A trip of a project changed, removed or added by hand (PRJ-111).

    Rentalars determines the trips of a project from its phases and
    subrentals (PRJ-097, ``projects.trips``); they stay the default. An
    adjustment names one of them by ``trip_key`` – ``to_venue-12`` (kind and
    phase), ``pickup`` or ``return`` – and replaces what is filled in:
    departure, start address, stops, destination, title, note. Empty fields
    and ``stops`` of ``None`` keep what Rentalars determines. ``is_removed``
    leaves the trip out. Deleting the adjustment ("zurücksetzen") brings
    the determined trip back. With an empty ``trip_key`` it is a trip of its
    own, with every value its own. An adjustment whose trip is gone – its
    phase was removed – is kept but changes nothing.
    """

    project = models.ForeignKey(
        Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="trip_adjustments"
    )
    trip_key = models.CharField(
        _("trip"), max_length=40, blank=True, help_text=_("Empty: a trip of its own, added by hand.")
    )
    is_removed = models.BooleanField(_("removed"), default=False)
    title = models.CharField(_("title"), max_length=120, blank=True)
    start = models.DateTimeField(_("departure"), null=True, blank=True)
    origin = models.CharField(_("start"), max_length=250, blank=True)
    #: The addresses of the stops in order; ``None``: the stops Rentalars determines.
    stops = models.JSONField(_("stops"), null=True, blank=True)
    destination = models.CharField(_("destination"), max_length=250, blank=True)
    note = models.CharField(_("note"), max_length=500, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("changed by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    changed_at = models.DateTimeField(_("changed"), default=timezone.now, editable=False)

    audit_exclude = frozenset({"changed_at"})

    class Meta:
        verbose_name = _("changed trip")
        verbose_name_plural = _("changed trips")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.project} – {self.trip_key or self.title}"

    def audit_parent(self) -> models.Model | None:
        """Show the change in the history of the project (PRJ-032)."""
        return self.project


# --- Logistics: vehicles and trailers of a project (LOG-001 ff.) ------------------------------------


class VehicleBilling(models.TextChoices):
    """LOG-005: how a booked vehicle is billed. A motor vehicle always per kilometre; a trailer either way."""

    KM = "km", _("per kilometre")
    DAY = "day", _("per day")


class TripBilling(models.TextChoices):
    """LOG-007: which kilometres of a trip are charged – chosen per trip."""

    DRIVEN = "driven", _("driven kilometres")
    PLANNED = "planned", _("planned kilometres")
    FLAT = "flat", _("flat rate for the trip")


def vehicle_name(item: Any) -> str:
    """How a vehicle of the fleet is named in short: its licence plate, else its ID (LOG-002)."""
    try:
        plate = item.vehicle.licence_plate
    except models.ObjectDoesNotExist:
        plate = ""
    return plate or item.display_id


class VehicleLine(AuditedModel):
    """A vehicle or trailer booked for a project – a line of the block "Logistik" (LOG-001).

    Like a crew line it stands below the personnel, never in a group, and it
    names a *product* (the rates, LOG-005) and, once chosen, the *vehicle*
    itself (an item of that product, LOG-002) – without one it is an open
    booking, like an open place of the crew. A vehicle from a supplier
    (``supplier``) has no item; what the supplier charges is its cost
    (``subrental_cost``), its price for the customer the rates of its
    product, as for an own vehicle.

    The booking runs from ``start`` to ``end`` – by default the project's,
    or the phase's. Over this period the vehicle is booked: two bookings of
    the same vehicle that overlap are pointed out (LOG-004).

    The price for the customer
        is copied from the product when the line is made and is the line's
        own from then on (PRJ-015): ``price_per_km``, for a motor vehicle
        ``trailer_surcharge_per_km`` – added on every trip with a trailer
        (LOG-006) –, for a trailer ``price_per_day`` and ``billing``. The
        kilometres come from the trips the vehicle drives
        (``TripVehicle``, LOG-007); a trailer per day is charged the rental
        days of the booking as material is (typed in ``rental_days``, else
        the period's or the project's), with the rental scale – or, with
        ``only_trip_days``, the days on which it drives. ``discount_percent``
        lowers the amount, at most to the product's maximum discount.

    The cost for the company (LOG-010)
        ``cost_per_km`` and ``cost_per_day`` are copied from the product;
        visible only with the right to see purchase prices (AUT-019).
    """

    project = models.ForeignKey(
        Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="vehicle_lines"
    )
    product = models.ForeignKey(
        Product, verbose_name=_("vehicle product"), on_delete=models.PROTECT, related_name="vehicle_lines"
    )
    item = models.ForeignKey(
        "material.MaterialItem",
        verbose_name=_("vehicle"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vehicle_lines",
        help_text=_("Empty: not chosen yet, or from a supplier."),
    )
    title = models.CharField(_("title"), max_length=200)
    position = models.PositiveIntegerField(_("position"), default=0)
    phase = models.ForeignKey(
        "ProjectPhase",
        verbose_name=_("phase"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vehicle_lines",
    )
    start = models.DateTimeField(_("from"))
    end = models.DateTimeField(_("until"))
    note = models.TextField(_("note"), blank=True)

    # --- Price for the customer (LOG-005, LOG-006) -----------------------------
    billing = models.CharField(_("billing"), max_length=4, choices=VehicleBilling.choices, default=VehicleBilling.KM)
    price_per_km = models.DecimalField(
        _("price per kilometre"),
        max_digits=8,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    trailer_surcharge_per_km = models.DecimalField(
        _("trailer surcharge per kilometre"),
        max_digits=8,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Added to the price per kilometre on every trip with a trailer."),
    )
    price_per_day = models.DecimalField(
        _("price per day"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    rental_days = models.PositiveSmallIntegerField(
        _("rental days"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text=_("Empty: as material – the days of the booking's own period, else the project's rental days."),
    )
    only_trip_days = models.BooleanField(
        _("only days with trips"),
        default=False,
        help_text=_("Per day: count only the days on which the trailer drives, not the rental days."),
    )
    scale_version = models.ForeignKey(
        RentalScaleVersion,
        verbose_name=_("rental scale"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vehicle_lines",
        editable=False,
    )
    discount_percent = models.DecimalField(
        _("discount in percent"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    tax_rate = models.ForeignKey(
        TaxRate, verbose_name=_("tax rate"), on_delete=models.PROTECT, related_name="vehicle_lines"
    )

    # --- Cost for the company (LOG-010) ----------------------------------------
    cost_per_km = models.DecimalField(
        _("internal cost per kilometre"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    cost_per_day = models.DecimalField(
        _("internal cost per day"),
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    supplier = models.ForeignKey(
        Supplier,
        verbose_name=pgettext_lazy("subrental", "supplier"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vehicle_lines",
        help_text=_("Only for a vehicle from a supplier."),
    )
    subrental_cost = models.DecimalField(
        _("what the supplier charges"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("For the whole booking; it is the cost instead of the costs per kilometre and day."),
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    audit_sensitive = {
        "price_per_km": SpecialRight.PRICES,
        "trailer_surcharge_per_km": SpecialRight.PRICES,
        "price_per_day": SpecialRight.PRICES,
        "discount_percent": SpecialRight.PRICES,
        "cost_per_km": SpecialRight.PURCHASE_PRICES,
        "cost_per_day": SpecialRight.PURCHASE_PRICES,
        "subrental_cost": SpecialRight.PURCHASE_PRICES,
    }

    class Meta:
        verbose_name = _("vehicle booking")
        verbose_name_plural = _("vehicle bookings")
        ordering = ["position", "id"]
        indexes = [models.Index(fields=["item", "start", "end"], name="vehicle_line_period_idx")]

    def __str__(self) -> str:
        return self.label

    def audit_parent(self) -> models.Model | None:
        """Show logistics changes in the history of the project (PRJ-032)."""
        return self.project

    @property
    def label(self) -> str:
        """The booking in short: "Sprinter (B-RL 123)", or with "open" while no vehicle is chosen."""
        if self.item_id is not None:
            return f"{self.title} ({vehicle_name(self.item)})"
        if self.supplier_id is not None:
            return f"{self.title} ({self.supplier.name})"
        return str(self.title)

    @property
    def crew_label(self) -> str:
        """The booking as the crew sees it (deployment views, crew sheet): without the supplier of a rented one.

        Who only sees the deployments does not see the purchase
        side – the supplier stays with the planners (``label``).
        """
        if self.item_id is not None:
            return self.label
        return str(self.title)

    @property
    def is_car(self) -> bool:
        """Whether a motor vehicle is booked – from the product (LOG-005)."""
        return self.product.is_car

    @property
    def is_trailer(self) -> bool:
        """Whether a trailer is booked – from the product (LOG-005)."""
        return self.product.is_trailer

    @property
    def is_open(self) -> bool:
        """Whether the vehicle is still to be chosen: no vehicle, no supplier (like an open place, PRJ-020)."""
        return self.item_id is None and self.supplier_id is None

    @property
    def is_subrental(self) -> bool:
        """Whether the vehicle comes from a supplier (PRJ-018)."""
        return self.supplier_id is not None

    @property
    def is_billed_per_day(self) -> bool:
        """Whether the customer pays per day – only a trailer can be (LOG-005)."""
        return self.billing == VehicleBilling.DAY

    def has_own_period(self, project: Project | None = None) -> bool:
        """Whether the booking runs at other times than its project – its rental days follow its period."""
        project = project or self.project
        return (self.start, self.end) != (project.start, project.end)

    def clean(self) -> None:
        """LOG-002, LOG-005: a vehicle product, a vehicle of it, the period, the billing of a motor vehicle."""
        super().clean()
        errors: dict[str, Any] = {}
        if self.start and self.end and self.end <= self.start:
            errors["end"] = _("The end must be after the start.")
        if self.product_id is not None:
            if self.product.kind != ProductKind.VEHICLE:
                errors["product"] = _("Choose a vehicle or a trailer of the fleet.")
            elif self.product.is_car and self.billing != VehicleBilling.KM:
                errors["billing"] = _("A motor vehicle is billed per kilometre.")
        if self.item_id is not None and self.product_id is not None and self.item.product != self.product:
            errors["item"] = _("Choose a vehicle of the product %(product)s.") % {"product": self.product.name}
        if self.item_id is not None and self.supplier_id is not None:
            errors["supplier"] = _("A vehicle of your own comes from no supplier. Leave one of the two empty.")
        if self.phase_id and self.project_id and self.phase.project_id != self.project_id:
            errors["phase"] = _("Choose a phase of this project.")
        if errors:
            raise ValidationError(errors)


class TripVehicle(AuditedModel):
    """A vehicle on a trip of its project – with a trailer or without, and the kilometres (LOG-006, LOG-007).

    The trips are those Rentalars determines from the phases or that were
    added by hand (PRJ-097, PRJ-111); ``trip_key`` names one, as an
    adjustment of a trip does. A trip can be driven by several vehicles,
    each pulling at most one trailer (a combination has one trailer). A
    vehicle drives a trip once.

    Kilometres: planned and driven, typed in or suggested by the route
    service (LOG-017). ``billing`` says which are charged: the driven ones
    – until they are known the planned ones stand in as an estimate –, the
    planned ones, or a flat rate for the trip (vehicle, surcharge and a
    trailer billed per kilometre together).

    A trip that is gone – its phase was deleted, it was removed – keeps its
    vehicles; the logistics points them out to move or delete.
    """

    project = models.ForeignKey(
        Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="trip_vehicles"
    )
    trip_key = models.CharField(_("trip"), max_length=40)
    vehicle_line = models.ForeignKey(
        VehicleLine, verbose_name=_("vehicle"), on_delete=models.CASCADE, related_name="trip_uses"
    )
    trailer_line = models.ForeignKey(
        VehicleLine,
        verbose_name=_("trailer"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trailer_uses",
    )
    planned_km = models.DecimalField(
        _("planned kilometres"),
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    driven_km = models.DecimalField(
        _("driven kilometres"),
        max_digits=8,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    billing = models.CharField(_("charged"), max_length=8, choices=TripBilling.choices, default=TripBilling.DRIVEN)
    flat_price = models.DecimalField(
        _("flat rate for the trip"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    note = models.CharField(_("note"), max_length=500, blank=True)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    audit_sensitive = {"flat_price": SpecialRight.PRICES}

    class Meta:
        verbose_name = _("vehicle on a trip")
        verbose_name_plural = _("vehicles on trips")
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle_line", "trip_key"],
                name="trip_vehicle_once_per_trip",
                violation_error_message=_("This vehicle drives this trip already."),
            )
        ]

    def __str__(self) -> str:
        return f"{self.trip_key}: {self.vehicle_line}"

    def audit_parent(self) -> models.Model | None:
        """Show the change in the history of the project (PRJ-032)."""
        return self.project

    @property
    def charged_km(self) -> Decimal | None:
        """The kilometres charged: driven or planned as chosen; driven ones missing – the planned ones."""
        if self.billing == TripBilling.PLANNED:
            return self.planned_km
        return self.driven_km if self.driven_km is not None else self.planned_km

    @property
    def km_is_estimate(self) -> bool:
        """Whether the driven kilometres are charged but still unknown – the planned ones stand in (LOG-007)."""
        return self.billing == TripBilling.DRIVEN and self.driven_km is None

    @property
    def cost_km(self) -> Decimal | None:
        """The kilometres for the internal costs: driven, else planned – whatever is charged (LOG-010)."""
        return self.driven_km if self.driven_km is not None else self.planned_km

    def clean(self) -> None:
        """LOG-006, LOG-007: a motor vehicle of this project pulls a trailer of this project; a flat rate has its price."""
        super().clean()
        errors: dict[str, Any] = {}
        if self.vehicle_line_id is not None:
            if self.project_id and self.vehicle_line.project_id != self.project_id:
                errors["vehicle_line"] = _("Choose a vehicle booked in this project.")
            elif not self.vehicle_line.is_car:
                errors["vehicle_line"] = _("A trip is driven by a motor vehicle; a trailer is pulled by one.")
        if self.trailer_line_id is not None:
            if self.project_id and self.trailer_line.project_id != self.project_id:
                errors["trailer_line"] = _("Choose a trailer booked in this project.")
            elif not self.trailer_line.is_trailer:
                errors["trailer_line"] = _("Choose a trailer.")
            elif (
                self.trip_key
                and TripVehicle.objects.filter(project_id=self.project_id, trip_key=self.trip_key)
                .filter(trailer_line_id=self.trailer_line_id)
                .exclude(pk=self.pk)
                .exists()
            ):
                errors["trailer_line"] = _("This trailer is pulled by another vehicle on this trip.")
        if self.billing == TripBilling.FLAT and self.flat_price is None:
            errors["flat_price"] = _("Enter the flat rate for the trip.")
        if errors:
            raise ValidationError(errors)


# --- Related projects and service cases (PRJ-119) --------------------------------------------------------------


class ProjectRelation(AuditedModel):
    """Two projects or service cases that belong together (PRJ-119).

    The relation is symmetric and stored once: ``first`` is the one with the
    smaller ID, ``second`` the other (``projects.relations.pair``). A project
    can be related to any number of others; a whole project or a service case,
    never a subproject – its whole project is related instead. The note says
    in a few words how the two belong together ("Reklamation zu …").

    Linking and unlinking write an event into the history of *both* sides
    (``projects.relations``), with the number of the other one only: the
    reader of one side may not be allowed to open the other (AUT-016). The
    row itself names the two numbers only (:meth:`__str__`), for the same
    reason. Deleting one of the two deletes the relation; the other side notes
    it (:func:`_note_relations_of_deleted_project`).
    """

    first = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="+")
    second = models.ForeignKey(Project, verbose_name=_("related project"), on_delete=models.CASCADE, related_name="+")
    note = models.CharField(_("note"), max_length=200, blank=True)
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        verbose_name = _("project relation")
        verbose_name_plural = _("project relations")
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["first", "second"], name="project_relation_unique"),
            models.CheckConstraint(condition=models.Q(first__lt=models.F("second")), name="project_relation_ordered"),
        ]

    def __str__(self) -> str:
        # The numbers only: the change log of one side must not name what the other is called (AUT-016).
        return f"{self.first.number} ↔ {self.second.number}"

    def other_than(self, project: Project | int) -> Project:
        """The other side of the relation, seen from ``project``."""
        pk = project if isinstance(project, int) else project.pk
        return self.second if self.first_id == pk else self.first


def _note_relations_of_deleted_project(sender: Any, instance: Project, **kwargs: Any) -> None:
    """PRJ-119: a project that is deleted takes its relations along; the other sides note it."""
    from rentalars.core.audit import record_event

    if instance.pk is None:
        return
    for relation in ProjectRelation.objects.filter(models.Q(first=instance) | models.Q(second=instance)).select_related(
        "first", "second"
    ):
        record_event(relation.other_than(instance), "project.relation_deleted", {"number": instance.number})


models.signals.pre_delete.connect(
    _note_relations_of_deleted_project, sender=Project, dispatch_uid="projects.relations.deleted_project"
)


def _remember_lines_of_deleted_item(sender: Any, instance: Any, **kwargs: Any) -> None:
    """(R3-1) Before an item is deleted: note the lines that name it as their first wished item.

    The foreign key is cleared by the deletion itself, which happens after this signal; the lines are promoted
    in :func:`_promote_next_wished_item`.
    """
    instance._pinned_line_ids = list(
        MaterialLine.objects.filter(preferred_item_id=instance.pk).values_list("pk", flat=True)
    )


def _promote_next_wished_item(sender: Any, instance: Any, **kwargs: Any) -> None:
    """(R3-1) After an item is deleted: the first remaining further item becomes the preferred one.

    ``preferred_item`` is the first of the wished items and the planning reads the others only through it. Without
    this a line that lost its first item would keep further pins nobody sees – and that still count as rivals.
    """
    for line_id in getattr(instance, "_pinned_line_ids", ()):
        line = MaterialLine.objects.filter(pk=line_id, preferred_item__isnull=True).first()
        if line is None:
            continue
        promoted = line.further_preferred_items.order_by("inventory_number").first()
        if promoted is not None:
            MaterialLine.objects.filter(pk=line_id).update(preferred_item=promoted)
            line.further_preferred_items.remove(promoted)
    instance._pinned_line_ids = ()


models.signals.pre_delete.connect(
    _remember_lines_of_deleted_item, sender="material.MaterialItem", dispatch_uid="projects.wishes.remember"
)
models.signals.post_delete.connect(
    _promote_next_wished_item, sender="material.MaterialItem", dispatch_uid="projects.wishes.promote"
)

# Legacy import: the records of "Altprojekte importieren" live in a module of their own.
from rentalars.projects.legacy_models import LegacyImportBatch, LegacyImportItem  # noqa: E402, F401
