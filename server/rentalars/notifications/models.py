# SPDX-License-Identifier: GPL-3.0-or-later
"""Notifications in the application and by e-mail (UIX-005).

Something happened that a user should know about: a deployment request, an
answer to one, a change of a project, a shortage, a defect, a new mail. The
user finds it under the bell in the header and – unless switched off – in
the mailbox (UIX-005). Each user decides per kind (:class:`Preference`).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Kind(models.TextChoices):
    """What a notification is about (UIX-005, EML-018, EML-023, EML-032, NFA-018, PER-016, PRJ-105)."""

    DEPLOYMENT_REQUEST = "deployment_request", _("Deployment request")
    DEPLOYMENT_ANSWER = "deployment_answer", _("Answer to a deployment request")
    PROJECT_CHANGE = "project_change", _("Change of a project")
    SHORTAGE = "shortage", _("Shortage")
    DEFECT = "defect", _("Defect reported")
    NEW_MAIL = "new_mail", _("New mail for a project")
    MAIL_PROBLEM = "mail_problem", _("Problem fetching mails")
    SYSTEM_ERROR = "system_error", _("Error of the application")
    LOW_STOCK = "low_stock", _("Stock below the minimum")
    INSPECTION_DUE = "inspection_due", _("Inspections due")
    QUALIFICATION_EXPIRY = "qualification_expiry", _("Qualification expiring")
    JOB_FINISHED = "job_finished", _("A task in the background is finished")
    #: PER-022, PER-023: the person's own linked or CalDAV calendar keeps failing.
    CALENDAR_PROBLEM = "calendar_problem", _("Problem with my calendar")
    #: PRJ-105: the day of a follow-up of a project has come.
    FOLLOW_UP = "follow_up", _("Follow-up of a project")
    #: UIX-010: somebody mentioned the user with @ in the chat of a project.
    CHAT_MENTION = "chat_mention", _("Mentioned in a project chat")
    #: ADM-013: an automation ("if … then …") asks to tell the user.
    AUTOMATION = "automation", _("Message of an automation")
    #: ZEI-019: an own expense was sent back or reimbursed.
    EXPENSE = "expense", _("My expenses sent back or reimbursed")
    #: PRJ-108: somebody added the user's person to a service case.
    SERVICE_CASE = "service_case", _("Added to a service case")
    #: DOK-015: a closed project has no invoice yet.
    INVOICE_REMINDER = "invoice_reminder", _("Invoice still to be written")
    #: PRJ-118: the own deployment was planned firmly, changed or taken away (PER-016, PRJ-019).
    DEPLOYMENT_CHANGE = "deployment_change", _("Change of my deployment")
    #: ZEI-029: times are waiting for the approval of the user (ZEI-013).
    TIMES_TO_APPROVE = "times_to_approve", _("Times waiting for my approval")
    #: ZEI-031: the own times were approved, corrected by the approver or sent back (ZEI-012).
    TIME_DECISION = "time_decision", _("My times approved, corrected or sent back")
    #: PER-038: a freelancer made a price offer for a deployment request, or answered a counter-offer.
    PRICE_OFFER = "price_offer", _("Price offer of a freelancer")
    #: PER-038: the own price offer was accepted, rejected or countered.
    PRICE_OFFER_ANSWER = "price_offer_answer", _("Answer to my price offer")
    #: PRJ-072: a product was changed that is planned in a project not confirmed yet.
    PRODUCT_CHANGE = "product_change", _("Product changed in a project not yet fully confirmed")


#: Kinds that go by e-mail unless the user switches them off. A change of a
#: project happens often; it stays in the application unless asked for.
EMAIL_BY_DEFAULT = frozenset(
    {
        Kind.DEPLOYMENT_REQUEST,
        Kind.DEPLOYMENT_ANSWER,
        Kind.SHORTAGE,
        Kind.DEFECT,
        Kind.NEW_MAIL,
        Kind.MAIL_PROBLEM,
        Kind.SYSTEM_ERROR,
        Kind.CALENDAR_PROBLEM,
        Kind.LOW_STOCK,
        Kind.INSPECTION_DUE,
        Kind.QUALIFICATION_EXPIRY,
        Kind.FOLLOW_UP,
        Kind.CHAT_MENTION,
        Kind.AUTOMATION,
        Kind.EXPENSE,  # ZEI-019
        Kind.SERVICE_CASE,  # PRJ-108
        Kind.INVOICE_REMINDER,  # DOK-015
        Kind.DEPLOYMENT_CHANGE,  # PRJ-118
        Kind.TIMES_TO_APPROVE,  # ZEI-029
        Kind.TIME_DECISION,  # ZEI-031
        Kind.PRICE_OFFER,  # PER-038
        Kind.PRICE_OFFER_ANSWER,  # PER-038
    }
)

#: UIX-039: kinds the companion app shows on the phone unless the user switches them off – those that
#: concern the person directly and want an answer soon. The server only stores the choice; the app asks for it.
COMPANION_BY_DEFAULT = frozenset(
    {
        Kind.DEPLOYMENT_REQUEST,
        Kind.CHAT_MENTION,
        Kind.FOLLOW_UP,
        Kind.SERVICE_CASE,  # PRJ-108: somebody is waiting for the person
        Kind.DEPLOYMENT_CHANGE,  # PRJ-118: new times, another meeting point, taken off – needed on the way
    }
)

#: (UIX-052; UIX-005): how the settings – page and API – name a kind whose own name does
#: not say enough. "A task in the background is finished" is also what the AI sends when it is done, and the user
#: did not find it under that name. The list of notifications keeps the short name.
SETTING_LABELS = {
    Kind.JOB_FINISHED: _(
        "A task in the background is finished (e.g. AI summary, reply draft, reading an invoice, export)"
    ),
}

#: (UIX-052; UIX-005): kinds a user deliberately cannot switch off, each with the
#: reason (a lazy text, shown when somebody tries). They are left out of the settings (page and API) and always go in Rentalars, by e-mail and in the app
#: as the defaults say. Every other kind is switchable; ``tests/unit/test_093_notifications.py`` fails for a kind
#: that is neither in the settings nor here. None so far: what must reach somebody whatever they chose – a changed
#: e-mail address or password (AUT-030) – is a mail of the account (``accounts.notices``), not a notification.
ALWAYS_SENT: dict[str, Any] = {}


class Notification(models.Model):
    """One notification for one user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("user"), on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(_("kind"), max_length=24, choices=Kind.choices)
    title = models.CharField(_("title"), max_length=250)
    body = models.TextField(_("text"), blank=True)
    url = models.CharField(_("link"), max_length=500, blank=True)
    project = models.ForeignKey(
        "projects.Project",
        verbose_name=_("project"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    read_at = models.DateTimeField(_("read"), null=True, blank=True)
    emailed_at = models.DateTimeField(_("sent by e-mail"), null=True, blank=True)
    # UIX-039: whether the user wants it on the phone (the companion app), as set when it was created.
    companion = models.BooleanField(_("in the companion app"), default=False)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read_at"], name="notification_unread_idx")]

    def __str__(self) -> str:
        return self.title

    @property
    def is_read(self) -> bool:
        """Whether the user has seen it."""
        return self.read_at is not None


class Preference(models.Model):
    """Whether a user wants notifications of one kind, and how (UIX-005: "je Nutzer abschaltbar")."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    kind = models.CharField(_("kind"), max_length=24, choices=Kind.choices)
    in_app = models.BooleanField(_("in the application"), default=True)
    by_email = models.BooleanField(_("by e-mail"), default=True)
    # UIX-039: shown as a notification on the phone by the companion app ("In der App").
    companion = models.BooleanField(_("in the companion app"), default=False)

    class Meta:
        verbose_name = _("notification setting")
        verbose_name_plural = _("notification settings")
        constraints = [models.UniqueConstraint(fields=["user", "kind"], name="notification_preference_once")]

    def __str__(self) -> str:
        return f"{self.user} {self.kind}"


class ShortageNotice(models.Model):
    """A shortage that was already reported, so that the nightly check reports it only once."""

    line = models.ForeignKey("projects.MaterialLine", on_delete=models.CASCADE, related_name="+")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveIntegerField(default=0)
    reported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["line", "product"], name="shortage_notice_once")]

    def __str__(self) -> str:
        return f"{self.line_id}/{self.product_id}: {self.quantity}"


class StockNotice(models.Model):
    """A product whose stock fell below its minimum and was reported (PRD-020).

    Reported once; the notice is removed when the stock is back above the
    minimum, so that the next shortfall is reported again.
    """

    product = models.OneToOneField("products.Product", on_delete=models.CASCADE, related_name="+")
    stock = models.IntegerField(default=0)
    reported_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.product_id}: {self.stock}"


class DueNotice(models.Model):
    """Something with a due date that was already reported: an inspection, a qualification.

    ``key`` names it, e.g. ``inspection:42:3:2027-03-01`` (item, type, due
    date) – a new due date is a new notice.
    """

    key = models.CharField(max_length=120, unique=True)
    reported_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.key


class InvoiceNotice(models.Model):
    """DOK-015: when a project without invoice was last reminded of, and how often.

    Removed when the project gets its invoice, is marked as invoiced or as
    "no invoice", or is opened again – so that a project closed once more
    starts its reminders anew.
    """

    project = models.OneToOneField("projects.Project", on_delete=models.CASCADE, related_name="+")
    first_reminded_at = models.DateTimeField(default=timezone.now)
    last_reminded_at = models.DateTimeField(default=timezone.now)
    count = models.PositiveIntegerField(default=1)

    def __str__(self) -> str:
        return f"{self.project_id}: {self.count}"


class ApprovalNotice(models.Model):
    """ZEI-029 (ZEI-013): when a user was last reminded of times waiting for approval.

    One row per user who may approve times. Removed when nothing waits for
    the user any more, so that the next time handed in starts the reminders
    anew (the first one after the days set).
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    first_reminded_at = models.DateTimeField(default=timezone.now)
    last_reminded_at = models.DateTimeField(default=timezone.now)
    count = models.PositiveIntegerField(default=1)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.count}"
