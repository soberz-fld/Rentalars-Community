# SPDX-License-Identifier: GPL-3.0-or-later
"""Company-wide settings of notifications: shortages (VFG-036), invoices (DOK-015), times to approve (ZEI-029).

Einstellungen → Benachrichtigungen. The
company chooses the time of day, how often (every day, on working days, once
a week, never), how far ahead and whether shortages already reported are
reported again at every check. The defaults were the behaviour;
VFG-036, DOK-015: known
shortages are reported again at every check – one reminder per project – and
done service cases are reminded of their invoice as well; both are switched on by default. Service
cases are reminded of only once done after "service cases too" was switched on
(``invoice_cases_since``), else every
case done earlier would be reminded of at once.

The check itself rides on the minute timer of the tasks in the background
(``run_jobs``, ``rentalars-jobs.timer``), which every installation has: the
time is a value in the database, so no timer of the operating system has to
be changed (that would need root). See :mod:`rentalars.notifications.schedule`.

Imported at the end of ``rentalars/core/models.py`` so that Django finds it.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.dates import WEEKDAYS
from django.utils.translation import gettext_lazy as _

from rentalars.core.models import SingletonModel

#: VFG-036: how far ahead shortages are reported – the four weeks, at most half a year.
DEFAULT_LEAD_WEEKS = 4
MAX_LEAD_WEEKS = 26
#: VFG-036: the default time of the check.
DEFAULT_SHORTAGE_TIME = datetime.time(4, 15)

#: DOK-015: reminders of open invoices – the first one this many days after a project was closed, then again.
DEFAULT_INVOICE_FIRST_DAYS = 1
DEFAULT_INVOICE_EVERY_DAYS = 7
MAX_INVOICE_DAYS = 60
DEFAULT_INVOICE_TIME = datetime.time(9, 0)

#: ZEI-029 (ZEI-013): who may approve times is reminded of those waiting – at this time, the
#: first time once a time has waited this many days since it was handed in, then again every few days.
DEFAULT_APPROVAL_TIME = datetime.time(8, 0)
DEFAULT_APPROVAL_FIRST_DAYS = 1
DEFAULT_APPROVAL_EVERY_DAYS = 1
MAX_APPROVAL_DAYS = 60

#: Written by the check alone (queryset updates), never by saving the settings, and not in the change log.
BOOKKEEPING_FIELDS = frozenset(
    {
        "shortage_last_run",
        "shortage_checked_at",
        "shortage_reported",
        "invoice_reminders_since",
        "invoice_cases_since",
        "invoice_last_run",
        "invoice_checked_at",
        "invoice_reminded",
        "approval_last_run",
        "approval_checked_at",
        "approval_reminded",
    }
)

#: ISO weekdays (1 Monday … 7 Sunday) with their full names, as Django translates them.
ISO_WEEKDAY_CHOICES = [(number, WEEKDAYS[number - 1]) for number in range(1, 8)]


class ShortageInterval(models.TextChoices):
    """How often shortages are reported (VFG-036)."""

    DAILY = "daily", _("Every day")
    WORKDAYS = "workdays", _("On working days (Monday to Friday, except holidays)")
    WEEKLY = "weekly", _("Once a week")
    OFF = "off", _("Never – switched off")


class NotificationSettings(SingletonModel):
    """When and how far ahead the project managers are told about shortages (VFG-036, UIX-005).

    ``shortage_last_run``, ``shortage_checked_at`` and ``shortage_reported``
    are bookkeeping of the check, written by the check alone (queryset
    updates): saving the settings never writes them back with the values a
    form or the API loaded before.
    """

    shortage_interval = models.CharField(
        _("how often"),
        max_length=10,
        choices=ShortageInterval.choices,
        default=ShortageInterval.DAILY,
        help_text=_("“On working days” leaves out the holidays set under Settings → Surcharges."),
    )
    shortage_weekday = models.PositiveSmallIntegerField(
        _("day of the week"),
        choices=ISO_WEEKDAY_CHOICES,
        default=1,
        help_text=_("For “Once a week”."),
    )
    shortage_time = models.TimeField(
        _("time of day"),
        default=DEFAULT_SHORTAGE_TIME,
        help_text=_("Rentalars checks within a minute of this time and reports what it finds."),
    )
    shortage_lead_weeks = models.PositiveSmallIntegerField(
        _("how far ahead (weeks)"),
        default=DEFAULT_LEAD_WEEKS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_LEAD_WEEKS)],
        help_text=_("Shortages of projects that begin within this many weeks – 1 to 26."),
    )
    # VFG-036: on by default; the update switches it on.
    shortage_repeat = models.BooleanField(
        _("report known shortages again at every check"),
        default=True,
        help_text=_(
            "Off: each shortage is reported once – again only if it grows, or if it was resolved and comes back. "
            "On: every check reminds of all open shortages again – one message per project."
        ),
    )
    # --- DOK-015: reminders of invoices not written yet ---------------------------------------------
    invoice_reminders = models.BooleanField(
        _("remind of invoices"),
        default=True,
        help_text=_(
            "Closed projects without invoice are reminded of until the invoice is made – or, with invoices written "
            "in another program, until “Invoice issued” is ticked."
        ),
    )
    invoice_time = models.TimeField(_("time of day"), default=DEFAULT_INVOICE_TIME)
    invoice_first_days = models.PositiveSmallIntegerField(
        _("first reminder after (days)"),
        default=DEFAULT_INVOICE_FIRST_DAYS,
        validators=[MaxValueValidator(MAX_INVOICE_DAYS)],
        help_text=_("Days after the day the project was closed; 0: at the next check after closing."),
    )
    invoice_every_days = models.PositiveSmallIntegerField(
        _("then again every (days)"),
        default=DEFAULT_INVOICE_EVERY_DAYS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_INVOICE_DAYS)],
    )
    invoice_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("also remind"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("Besides the project manager – and for projects without one. Empty: only the project manager."),
    )
    # DOK-015: on by default; the update switches it on.
    invoice_service_cases = models.BooleanField(
        _("service cases too"),
        default=True,
        help_text=_(
            "Done service cases with something to charge are reminded of as well – those done since the setting "
            "was switched on."
        ),
    )
    #: Projects closed before this moment are not reminded of.
    invoice_reminders_since = models.DateTimeField(null=True, blank=True, editable=False)
    #: DOK-015 (review: old service cases flooded): service cases done before this moment are not reminded
    #: of – set whenever "service cases too" is switched on (by the page or the API), so that
    #: the cases done while it was off do not all come at once. ``None``: no cut-off besides the one above.
    invoice_cases_since = models.DateTimeField(null=True, blank=True, editable=False)
    invoice_last_run = models.DateTimeField(null=True, blank=True, editable=False)
    invoice_checked_at = models.DateTimeField(_("last check"), null=True, blank=True, editable=False)
    invoice_reminded = models.PositiveIntegerField(_("reminded at the last check"), default=0, editable=False)
    # --- ZEI-029 (ZEI-013): times waiting for approval --------------------------------------------------
    approval_reminders = models.BooleanField(
        _("remind of times to approve"),
        default=True,
        help_text=_(
            "Everybody who may approve times is reminded of the times and expenses handed in and waiting for "
            "their approval – each only of those they may approve, not of their own."
        ),
    )
    approval_time = models.TimeField(_("time of day"), default=DEFAULT_APPROVAL_TIME)
    approval_first_days = models.PositiveSmallIntegerField(
        _("first reminder after (days)"),
        default=DEFAULT_APPROVAL_FIRST_DAYS,
        validators=[MaxValueValidator(MAX_APPROVAL_DAYS)],
        help_text=_("Days after the day a time was handed in; 0: at the next check after handing in."),
    )
    approval_every_days = models.PositiveSmallIntegerField(
        _("then again every (days)"),
        default=DEFAULT_APPROVAL_EVERY_DAYS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_APPROVAL_DAYS)],
        help_text=_("As long as times are waiting; 1: every day."),
    )
    approval_last_run = models.DateTimeField(null=True, blank=True, editable=False)
    approval_checked_at = models.DateTimeField(_("last check"), null=True, blank=True, editable=False)
    approval_reminded = models.PositiveIntegerField(_("reminded at the last check"), default=0, editable=False)

    #: The schedule counts from here: the last check, or when the time or the interval was changed.
    shortage_last_run = models.DateTimeField(null=True, blank=True, editable=False)
    #: When the check last ran, and how many shortages it reported – shown on the page and in the API.
    shortage_checked_at = models.DateTimeField(_("last check"), null=True, blank=True, editable=False)
    shortage_reported = models.PositiveIntegerField(_("reported at the last check"), default=0, editable=False)

    audit_exclude = BOOKKEEPING_FIELDS

    class Meta:
        verbose_name = _("notification settings of the company")
        verbose_name_plural = _("notification settings of the company")

    def __str__(self) -> str:
        return str(_("Notification settings of the company"))

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the settings; the time of the last check stays as the check wrote it (VFG-036).

        DOK-015: switching "service cases too" on sets:attr:`invoice_cases_since` to now – the
        form and the API both save here. Switched off and on again, the cut-off moves: the cases done while it
        was off are not reminded of, only listed (the filter "Rechnung offen", the start page).
        """
        rows = type(self).objects.filter(pk=1)
        stored = rows.values("invoice_service_cases").first()
        if "update_fields" not in kwargs and stored is not None:
            kwargs["update_fields"] = [
                field.name
                for field in self._meta.concrete_fields
                if not field.primary_key and field.name not in BOOKKEEPING_FIELDS
            ]
        super().save(*args, **kwargs)
        written = kwargs.get("update_fields") is None or "invoice_service_cases" in kwargs["update_fields"]
        if written and stored is not None and self.invoice_service_cases and not stored["invoice_service_cases"]:
            # Bookkeeping: a queryset update, never in the change log (BOOKKEEPING_FIELDS).
            self.invoice_cases_since = timezone.now()
            rows.update(invoice_cases_since=self.invoice_cases_since)
