# SPDX-License-Identifier: GPL-3.0-or-later
"""Automations with triggers: "if … then …" (ADM-013).

An :class:`Automation` is one rule, defined in the browser under
Einstellungen → Automationen: when something happens (the *trigger*, with a
condition), Rentalars does one thing (the *action*). Several things for the
same event are several rules.

Triggers
    * a mail without project tag arrives in a mailbox that takes such mails
      in (an inquiry, EML-041, EML-042) – optionally only in one mailbox;
    * a project reaches a status (PRJ-008) – by hand or by packing;
    * an answer to a deployment request arrives (PER-016, PER-032) – an
      acceptance, a refusal or either, in the browser, by mail or entered by
      the planner;
    * a follow-up of a project is due (PRJ-105);
    * PRJ-112: the follow-up of a service case is due – optionally
      only in one status of the case;
    * PRJ-112: new communication in a service case – a mail received or sent,
      a chat message; optionally only one kind of them and only in one status.
      Not the automations' own doings (``automations.engine``).

MAT-057: a reported defect is a trigger too; its actions are
creating a service case of it, putting it under Projekte → Anfragen, or
notifying somebody. A default rule creates the service case (start data in
the migration ``0001_squashed_0003_defects_085``).

Actions
    * answer the mail with a text – only for the trigger "inquiry"; this is
      the deliberate exception to EML-030, protected against loops
      (``automations.engine``);
    * notify a person: a chosen user, the project manager, the planner who
      asked (crew answer) or the user the follow-up is for;
    * note an open item in the project (PRJ-059);
    * PRJ-112: set the status of the service case – open, in progress or
      done (the other statuses need a follow-up a rule cannot choose);
    * MAT-057: create a service case of a defect report – title and
      description from the rule's subject and text with placeholders, the
      chosen user responsible; or only put the report under Projekte →
      Anfragen, where it becomes a service case by hand or is taken off.

Every installation has three active rules, which can be changed
or switched off: a case waiting to close is closed when its follow-up is due
and opened again on new communication; a case in the backlog is opened again
when its follow-up is due (``RULES`` of the migration
``0001_squashed_0003_defects_085``, which creates them in a new database).

(ADM-019) These four rules that come with Rentalars are
rules like any other – changed, switched off and deleted with the same rights
and checks. Each carries a stable key (``default_key``); "Standard-Automationen
wiederherstellen" creates the missing ones by it (``automations.defaults``).

Every execution is an :class:`AutomationRun`: what triggered it, what was
done – or why not – and when. The runs are listed below the rules and kept
for :data:`RUN_RETENTION_DAYS` days.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.core.audit import AuditedModel

#: How long the runs are kept (daily maintenance).
RUN_RETENTION_DAYS = 365

#: The longest open item (``projects.OpenItem.text``).
OPEN_ITEM_LENGTH = 250

#: MAT-057: the longest title of a service case (``projects.Project.name``) – before the placeholders are filled.
CASE_TITLE_LENGTH = 200


class Trigger(models.TextChoices):
    """What starts an automation (ADM-013)."""

    INQUIRY = "inquiry", _("a mail without project tag arrives")
    PROJECT_STATUS = "project_status", _("a project reaches a status")
    CREW_ANSWER = "crew_answer", _("an answer to a deployment request arrives")
    FOLLOW_UP = "follow_up", _("a follow-up is due")
    # PRJ-112
    CASE_FOLLOW_UP = "case_follow_up", _("the follow-up of a service case is due")
    CASE_COMMUNICATION = "case_communication", _("new communication in a service case")
    # MAT-057
    DEFECT = "defect", _("a defect is reported")


#: PRJ-112: the triggers of the service cases – with the status of the case as condition.
CASE_TRIGGERS = (Trigger.CASE_FOLLOW_UP.value, Trigger.CASE_COMMUNICATION.value)


class Action(models.TextChoices):
    """What an automation does (ADM-013)."""

    REPLY = "reply", _("answer the mail")
    NOTIFY = "notify", _("notify a person")
    OPEN_ITEM = "open_item", _("note an open item in the project")
    CASE_STATUS = "case_status", _("set the status of the service case")  # PRJ-112
    # MAT-057: of a defect report, a service case at once – or only an inquiry under Projekte → Anfragen.
    CREATE_CASE = "create_case", _("create a service case")
    CREATE_INQUIRY = "create_inquiry", _("put it under Projects → Inquiries")


class Communication(models.TextChoices):
    """PRJ-112: which communication in a service case starts the automation."""

    ANY = "", _("a mail received or sent, or a chat message")
    MAIL_IN = "mail_in", _("a mail received")
    MAIL_OUT = "mail_out", _("a mail sent")
    CHAT = "chat", _("a chat message")


#: PRJ-112: the statuses a rule can give a service case – those that need no follow-up.
TARGET_CASE_STATUSES = ("open", "in_progress", "done")


class Recipient(models.TextChoices):
    """Who a notification of an automation goes to."""

    USER = "user", _("a chosen user")
    MANAGER = "manager", _("the project manager")
    ASKED_BY = "asked_by", _("who asked for the deployment")
    FOLLOW_UP_USER = "follow_up_user", _("whom the follow-up is for")


class CrewAnswer(models.TextChoices):
    """Which answers to a deployment request start the automation."""

    ANY = "", _("acceptance or refusal")
    ACCEPTED = "accepted", _("acceptance")
    DECLINED = "declined", _("refusal")


#: The actions each trigger allows: an answer by mail only to a mail; an open item only where there is a project.
ACTIONS_OF = {
    Trigger.INQUIRY: (Action.REPLY, Action.NOTIFY),
    Trigger.PROJECT_STATUS: (Action.NOTIFY, Action.OPEN_ITEM),
    Trigger.CREW_ANSWER: (Action.NOTIFY, Action.OPEN_ITEM),
    Trigger.FOLLOW_UP: (Action.NOTIFY, Action.OPEN_ITEM),
    Trigger.CASE_FOLLOW_UP: (Action.CASE_STATUS, Action.NOTIFY, Action.OPEN_ITEM),
    Trigger.CASE_COMMUNICATION: (Action.CASE_STATUS, Action.NOTIFY, Action.OPEN_ITEM),
    Trigger.DEFECT: (Action.CREATE_CASE, Action.CREATE_INQUIRY, Action.NOTIFY),  # MAT-057
}

#: The recipients of a notification each trigger allows.
RECIPIENTS_OF = {
    Trigger.INQUIRY: (Recipient.USER,),
    Trigger.PROJECT_STATUS: (Recipient.USER, Recipient.MANAGER),
    Trigger.CREW_ANSWER: (Recipient.USER, Recipient.MANAGER, Recipient.ASKED_BY),
    Trigger.FOLLOW_UP: (Recipient.USER, Recipient.MANAGER, Recipient.FOLLOW_UP_USER),
    Trigger.CASE_FOLLOW_UP: (Recipient.USER, Recipient.MANAGER, Recipient.FOLLOW_UP_USER),
    Trigger.CASE_COMMUNICATION: (Recipient.USER, Recipient.MANAGER),
    Trigger.DEFECT: (Recipient.USER,),  # MAT-057
}


class Automation(AuditedModel):
    """One rule: "if <trigger and condition>, then <action>" (ADM-013)."""

    name = models.CharField(_("name"), max_length=120, help_text=_("Shown in the list and with every run."))
    is_active = models.BooleanField(_("active"), default=True, help_text=_("Switched off, the rule does nothing."))
    trigger = models.CharField(pgettext_lazy("automation", "if"), max_length=20, choices=Trigger.choices)
    # --- Conditions -------------------------------------------------------------------------------
    mailbox = models.ForeignKey(
        "mail.Mailbox",
        verbose_name=_("only in the mailbox"),
        null=True,
        blank=True,
        # EML-046: a mailbox can always be deleted; its rules are switched off first (``automations.signals``).
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("Empty: every mailbox that takes in mails without project tag."),
    )
    status = models.CharField(_("status"), max_length=20, blank=True)
    answer = models.CharField(
        pgettext_lazy("deployment request", "answer"),
        max_length=10,
        blank=True,
        choices=CrewAnswer.choices,
        default=CrewAnswer.ANY,
    )
    # PRJ-112: for the triggers of the service cases ``status`` is the status of the case (empty: any status);
    # for "new communication" this says which kind counts.
    communication = models.CharField(
        _("communication"), max_length=10, blank=True, choices=Communication.choices, default=Communication.ANY
    )
    # --- Action -----------------------------------------------------------------------------------
    action = models.CharField(pgettext_lazy("automation", "then"), max_length=20, choices=Action.choices)
    recipient = models.CharField(
        _("whom"), max_length=20, blank=True, choices=Recipient.choices, default=Recipient.USER
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # PRJ-112: the status the action "set the status of the service case" gives it.
    new_case_status = models.CharField(_("new status"), max_length=12, blank=True)
    subject = models.CharField(_("subject"), max_length=250, blank=True)
    text = models.TextField(_("text"), blank=True)
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
    # (ADM-019; ADM-013, PRJ-112, MAT-057): set for the rules that come with Rentalars – their
    # stable key, never their name, so that a renamed or changed default is still known. Empty (NULL) for the own
    # rules of a company; unique, so that restoring never makes a second one.
    default_key = models.CharField(
        _("default automation"),
        max_length=40,
        null=True,
        blank=True,
        unique=True,
        editable=False,
        help_text=_("Set for the automations that come with Rentalars."),
    )

    # The key is technical; who created or restored a rule is in the "created" entry.
    audit_exclude = frozenset({"created_at", "default_key"})

    class Meta:
        verbose_name = _("automation")
        verbose_name_plural = _("automations")
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_default(self) -> bool:
        """(ADM-019) Whether the rule came with Rentalars."""
        return bool(self.default_key)

    @property
    def default_changed(self) -> bool:
        """(ADM-019) Whether a rule that came with Rentalars differs from how it came."""
        from rentalars.automations.defaults import is_changed

        return is_changed(self)

    @property
    def status_label(self) -> str:
        """The status of the condition as shown, e.g. "Bestätigt" – PRJ-112: of the service case for its triggers."""
        from rentalars.projects.models import CaseStatus, ProjectStatus

        if self.trigger in CASE_TRIGGERS:
            return str(CaseStatus(self.status).label) if self.status in CaseStatus.values else ""
        return str(ProjectStatus(self.status).label) if self.status in ProjectStatus.values else self.status

    @property
    def new_case_status_label(self) -> str:
        """PRJ-112: the status the action gives the service case, as shown."""
        from rentalars.projects.models import CaseStatus

        return str(CaseStatus(self.new_case_status).label) if self.new_case_status in CaseStatus.values else ""

    def normalise(self) -> None:
        """Drop what does not belong to the trigger and the action, so that nothing hidden stays stored."""
        if self.trigger != Trigger.INQUIRY:
            self.mailbox = None
        if self.trigger != Trigger.PROJECT_STATUS and self.trigger not in CASE_TRIGGERS:
            self.status = ""
        if self.trigger != Trigger.CREW_ANSWER:
            self.answer = CrewAnswer.ANY
        if self.trigger != Trigger.CASE_COMMUNICATION:
            self.communication = Communication.ANY
        if self.action != Action.CASE_STATUS:
            self.new_case_status = ""
        else:
            self.subject = ""
            self.text = ""
        if self.action == Action.NOTIFY:
            self.recipient = self.recipient or Recipient.USER
            if self.recipient != Recipient.USER:
                self.user = None
        elif self.action == Action.CREATE_CASE:
            # MAT-057: ``user`` is who is responsible for the new service case (optional).
            self.recipient = ""
        else:
            self.recipient = ""
            self.user = None
        if self.action == Action.CREATE_INQUIRY:
            # MAT-057: ``subject`` is how the inquiry is listed; there is no text to write.
            self.text = ""
        if self.action == Action.OPEN_ITEM:
            self.subject = ""

    def problems(self) -> dict[str, str]:
        """What does not fit together, by field; empty if the rule can be stored (browser and API alike)."""
        from rentalars.projects.models import ProjectStatus

        errors: dict[str, str] = {}
        if self.trigger not in Trigger.values:
            errors["trigger"] = str(_("Choose what starts the automation."))
            return errors
        if self.action not in ACTIONS_OF[self.trigger]:
            errors["action"] = str(
                _("With this trigger the possible actions are: %(actions)s.")
                % {"actions": ", ".join(str(Action(choice).label) for choice in ACTIONS_OF[self.trigger])}
            )
            return errors
        if self.trigger == Trigger.INQUIRY and self.mailbox_id and not self.mailbox.process_untagged:
            errors["mailbox"] = str(
                _("This mailbox does not take in mails without project tag. Switch that on under E-mail first.")
            )
        if self.trigger == Trigger.PROJECT_STATUS and self.status not in ProjectStatus.values:
            errors["status"] = str(_("Choose the status."))
        if self.trigger in CASE_TRIGGERS:
            from rentalars.projects.models import CaseStatus

            if self.status and self.status not in CaseStatus.values:
                errors["status"] = str(_("Choose a status of a service case, or none for any status."))
            if self.communication not in Communication.values:
                errors["communication"] = str(_("Choose which communication counts."))
        if self.action == Action.CASE_STATUS:
            if self.new_case_status not in TARGET_CASE_STATUSES:
                errors["new_case_status"] = str(_("Choose the new status: open, in progress or done."))
            elif self.new_case_status == self.status:
                errors["new_case_status"] = str(_("The new status is the one of the condition – choose another."))
        if self.action == Action.NOTIFY:
            if self.recipient not in RECIPIENTS_OF[self.trigger]:
                errors["recipient"] = str(
                    _("With this trigger the notification can go to: %(whom)s.")
                    % {"whom": ", ".join(str(Recipient(choice).label) for choice in RECIPIENTS_OF[self.trigger])}
                )
            elif self.recipient == Recipient.USER and not self.user_id:
                errors["user"] = str(_("Choose the user to notify."))
        if self.action == Action.CREATE_CASE and len(self.subject) > CASE_TITLE_LENGTH:
            errors["subject"] = str(
                _("The title of a service case may have at most %(count)d characters.") % {"count": CASE_TITLE_LENGTH}
            )
        if self.action == Action.REPLY and not self.text.strip():
            errors["text"] = str(_("Write the text of the answer."))
        if self.action == Action.OPEN_ITEM:
            if not self.text.strip():
                errors["text"] = str(_("Write what is to be done."))
            elif len(self.text) > OPEN_ITEM_LENGTH:
                errors["text"] = str(
                    _("An open item may have at most %(count)d characters.") % {"count": OPEN_ITEM_LENGTH}
                )
        return errors


class RunStatus(models.TextChoices):
    """What became of one run of an automation."""

    PENDING = "pending", _("waiting")
    RUNNING = "running", _("running")
    DONE = "done", _("done")
    SKIPPED = "skipped", _("left out")
    FAILED = "failed", _("failed")


class AutomationRun(models.Model):
    """One execution of an automation: event, outcome, time (ADM-013: "every run is logged and visible").

    ``event_key`` names the event – a mail by its Message-ID, a status change,
    an answer, a follow-up – so that no rule runs twice for the same event.
    ``recipient`` is the address answered or the user notified; the limit of
    one answer per sender, rule and day counts by it. ``data`` keeps what the
    placeholders of the text are filled with.
    """

    automation = models.ForeignKey(
        Automation,
        verbose_name=_("automation"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="runs",
    )
    #: The name of the rule when it ran; kept when the rule is deleted.
    automation_name = models.CharField(_("name of the automation"), max_length=120)
    trigger = models.CharField(pgettext_lazy("automation", "if"), max_length=20, choices=Trigger.choices)
    action = models.CharField(pgettext_lazy("automation", "then"), max_length=20, choices=Action.choices)
    event_key = models.CharField(max_length=120)
    created_at = models.DateTimeField(_("time"), default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(_("finished"), null=True, blank=True)
    status = models.CharField(_("result"), max_length=10, choices=RunStatus.choices, default=RunStatus.PENDING)
    project = models.ForeignKey(
        "projects.Project",
        verbose_name=_("project"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    #: What happened, in a few words: "Mail von kunde@x.example: Anfrage Stadtfest", "2027-0001 → bestätigt".
    event = models.CharField(_("event"), max_length=300, blank=True)
    recipient = models.CharField(_("recipient"), max_length=300, blank=True)
    detail = models.TextField(_("detail"), blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("run of an automation")
        verbose_name_plural = _("runs of automations")
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["automation", "event_key"], name="automation_run_once")]
        indexes = [models.Index(fields=["status", "created_at"], name="automation_run_status_idx")]

    def __str__(self) -> str:
        return f"{self.automation_name}: {self.event}"
