# SPDX-License-Identifier: GPL-3.0-or-later
"""E-mails of projects (chapter 5.15).

Rentalars fetches mails from existing mailboxes and assigns them to
projects by a tag in the subject, e.g. ``[RL#2026-0042]`` (EML-008 ff.). Only assigned mails are touched; all
others stay in the inbox as they are (EML-006, EML-013).

* :class:`Mailbox` – one mailbox with IMAP and SMTP access and its roles:
  correspondence (fetched; exactly one of them sends the mails of the
  projects) and system (sends invitations and notifications). The passwords
  are stored encrypted (EML-002, EML-003, EML-041).
* :class:`MailSettings` – what holds for all mailboxes: the signature, the
  fetch interval, the size limit, how long mails are kept.
* :class:`ProjectMail` – a mail that belongs to a project, received or sent,
  with :class:`MailAttachment` for its attachments (EML-019, EML-020).
* :class:`UnknownTagMail` – a mail whose tag names no project, or – from a
  mailbox that takes them in – a mail without a tag: an inquiry. It stays in
  the inbox and appears under Projects → Inquiries to be assigned by hand
  (EML-014, EML-041, EML-042). Also an inquiry noted by hand,
  e.g. a phone call (EML-053).
* :class:`MailLogEntry` – the mail log: every mail that came in or went out,
  project mails and system mails alike, with what became of it and the
  mailbox it went through (EML-039, EML-041).
* :class:`CrewRequestMail` – a deployment request sent by mail, with the
  token by which its answer by reply mail is recognised (PER-032).
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.core.audit import AuditedModel
from rentalars.core.crypto import SecretUnreadableError, decrypt_secret, encrypt_secret
from rentalars.core.models import SingletonModel


class Security(models.TextChoices):
    """How the connection to the mail server is encrypted (EML-002)."""

    SSL = "ssl", _("SSL/TLS (port 993 or 465)")
    STARTTLS = "starttls", _("STARTTLS (port 143 or 587)")


class AfterAssignment(models.TextChoices):
    """What becomes of an assigned mail in its mailbox (EML-006, EML-041).

    EML-006: "only mark as read" leaves the mail in the inbox, read.
    The default stays "mark as read and move".
    """

    MOVE = "move", _("mark as read and move into a folder")
    READ = "read", _("only mark as read")
    DELETE = "delete", _("delete")
    KEEP = "keep", _("leave unchanged in the inbox")


class Untagged(models.TextChoices):
    """What becomes of a mail without project tag that came to an address of a mailbox (EML-047)."""

    IGNORE = "ignore", _("do not take in")
    INQUIRY = "inquiry", _("as an inquiry")
    SERVICE_CASE = "service_case", _("create a service case at once")


class Mailbox(AuditedModel):
    """A mailbox Rentalars fetches from or sends through (EML-041, EML-003, EML-002, EML-035).

    Its roles:

    * **Correspondence** (``for_correspondence``): new mails are fetched and
      assigned to projects by their tag. Several mailboxes may have it.
      Exactly one of the active ones is the mailbox for **outgoing**
      correspondence (``is_outgoing``): mails written in a project go out
      through it, with its address as sender.
    * **System** (``for_system``): invitations, password links and
      notifications go out through its SMTP server. Without such a mailbox
      they go through ``[email]`` of the configuration file.

    One mailbox may have both roles. At most one mailbox carries
    ``is_outgoing`` and at most one ``for_system``; giving the role to a
    mailbox takes it from the other (``mail.mailboxes.save_mailbox``).

    Per mailbox for incoming mails: whether mails **without** project tag are
    taken in as inquiries (``process_untagged``) or left alone, and what
    becomes of an assigned mail on the server (``after_assignment``).

    EML-047: further addresses that deliver into the mailbox
    (aliases) are :class:`MailboxAddress` rows (``aliases``), each with its
    own rule for mails without tag; ``process_untagged`` holds for the
    mailbox's own address and for every address not listed.

    EML-049: mails without tag are taken in only from
    ``untagged_since`` on – set to the moment the switch is turned on,
    changeable – and with ``untagged_unread_only`` only unread ones; the
    others stay in the inbox untouched (``mail.aliases.untagged_skip``).

    EML-052: ``sender_roles`` – the roles whose members may choose the
    address of a mailbox of the correspondence as sender of a project mail
    (``mail.senders``). The mailbox that sends the correspondence is free for
    everybody who may write correspondence.

    EML-026: ``signature_html`` – a signature of its own for the mails
    sent from the mailbox's addresses; empty means the common one
    (``MailSettings.signature_html``).

    The mailbox also holds the state of its fetch, for the settings and the
    self-check (EML-032).
    """

    name = models.CharField(
        _("name"), max_length=120, help_text=_("Shown in the list, in the mail log and with the inquiries.")
    )
    address = models.EmailField(
        _("address of the mailbox"), blank=True, help_text=_("The sender of mails sent through this mailbox.")
    )
    is_active = models.BooleanField(
        _("active"), default=True, help_text=_("Switched off, the mailbox is neither fetched nor used for sending.")
    )

    # --- Roles (EML-041) ---------------------------------------------------------------------
    for_correspondence = models.BooleanField(
        _("correspondence"),
        default=False,
        help_text=_("New mails are fetched and assigned to their project by the tag in the subject."),
    )
    is_outgoing = models.BooleanField(
        _("sends the correspondence"),
        default=False,
        help_text=_("Mails written in a project go out through this mailbox, with its address as sender."),
    )
    for_system = models.BooleanField(
        _("system mails"),
        default=False,
        help_text=_(
            "Invitations, password links and notifications go out through this mailbox. Without such a "
            "mailbox they go through the configuration of the server."
        ),
    )

    # --- Access (EML-002, EML-035) ------------------------------------------------------------
    imap_host = models.CharField(_("IMAP server"), max_length=200, blank=True)
    imap_port = models.PositiveIntegerField(_("IMAP port"), default=993, validators=[MaxValueValidator(65535)])
    imap_security = models.CharField(
        _("IMAP encryption"), max_length=10, choices=Security.choices, default=Security.SSL
    )
    imap_user = models.CharField(_("IMAP user"), max_length=200, blank=True)
    imap_password_encrypted = models.TextField(_("IMAP password"), blank=True, editable=False)

    smtp_host = models.CharField(_("SMTP server"), max_length=200, blank=True)
    smtp_port = models.PositiveIntegerField(_("SMTP port"), default=587, validators=[MaxValueValidator(65535)])
    smtp_security = models.CharField(
        _("SMTP encryption"), max_length=10, choices=Security.choices, default=Security.STARTTLS
    )
    # EML-035: most providers use the access data of the mailbox for sending as well.
    smtp_same_login = models.BooleanField(
        _("same user and password as for receiving (IMAP)"),
        default=True,
        help_text=_("Usual with most providers. Switch it off if sending needs access data of its own."),
    )
    smtp_user = models.CharField(
        _("SMTP user"), max_length=200, blank=True, help_text=_("Empty: send without logging in.")
    )
    smtp_password_encrypted = models.TextField(_("SMTP password"), blank=True, editable=False)

    # --- Incoming mails (EML-006, EML-013, EML-041) ----------------------------------------------
    inbox_folder = models.CharField(_("inbox folder"), max_length=120, default="INBOX")
    process_untagged = models.BooleanField(
        _("take in mails without project tag"),
        default=False,
        help_text=_(
            "They appear as inquiries under Projects and can be taken over into a project. "
            "Switched off, they stay in the inbox untouched. Holds for the address of the mailbox and every "
            "address not listed under “Further addresses”."
        ),
    )
    # EML-049: mails without tag are taken in only from a point in time, optionally only unread ones.
    untagged_since = models.DateTimeField(
        _("taken in from"),
        null=True,
        blank=True,
        help_text=_(
            "Only mails that arrived in the mailbox from this moment on are taken in; older ones stay in the "
            "inbox untouched. Set to the moment of switching on; empty means now."
        ),
    )
    untagged_unread_only = models.BooleanField(
        _("only unread mails"),
        default=False,
        help_text=_("Mails already read in the mailbox stay in the inbox untouched."),
    )
    after_assignment = models.CharField(
        _("assigned mails in the mailbox"),
        max_length=10,
        choices=AfterAssignment.choices,
        default=AfterAssignment.MOVE,
        help_text=_("Delete only when Rentalars is the only place where the mails are kept."),
    )
    done_folder = models.CharField(
        _("folder for assigned mails"),
        max_length=120,
        blank=True,
        default="Rentalars",
        help_text=_("Created if it does not exist."),
    )

    # --- Sending (EML-052, EML-026) ---------------------------------------------------------
    sender_roles = models.ManyToManyField(
        "accounts.Role",
        verbose_name=_("may send from this address"),
        blank=True,
        related_name="+",
        help_text=_(
            "Members of these roles may choose the address of this mailbox as sender of a mail written in a "
            "project. The mailbox that sends the correspondence is open to everybody who may write "
            "correspondence; superusers may use every address."
        ),
    )
    signature_html = models.TextField(_("signature of the mailbox"), blank=True)

    # --- State of fetching (EML-005, EML-032). Not part of the form. ---------------------------
    last_fetch_at = models.DateTimeField(_("last fetch"), null=True, blank=True, editable=False)
    last_success_at = models.DateTimeField(_("last successful fetch"), null=True, blank=True, editable=False)
    last_error = models.TextField(_("last error"), blank=True, editable=False)
    last_error_at = models.DateTimeField(_("last error at"), null=True, blank=True, editable=False)
    error_reported = models.BooleanField(default=False, editable=False)
    uid_validity = models.BigIntegerField(default=0, editable=False)
    last_uid = models.BigIntegerField(default=0, editable=False)

    audit_exclude = frozenset(
        {
            "imap_password_encrypted",
            "smtp_password_encrypted",
            "last_fetch_at",
            "last_success_at",
            "last_error",
            "last_error_at",
            "error_reported",
            "uid_validity",
            "last_uid",
        }
    )

    class Meta:
        verbose_name = _("mailbox")
        verbose_name_plural = _("mailboxes")
        ordering = ["name", "id"]
        constraints = [
            # Only a mailbox of the correspondence sends the mails of the projects.
            models.CheckConstraint(
                condition=models.Q(is_outgoing=False) | models.Q(for_correspondence=True),
                name="mail_outgoing_is_correspondence",
            )
        ]

    def __str__(self) -> str:
        return self.name or self.address or str(_("Mailbox"))

    # The passwords are written and read only through these methods; the
    # forms and the API never show them (EML-002).
    def set_imap_password(self, password: str) -> None:
        """Store the IMAP password encrypted."""
        self.imap_password_encrypted = encrypt_secret(password)

    def set_smtp_password(self, password: str) -> None:
        """Store the SMTP password encrypted."""
        self.smtp_password_encrypted = encrypt_secret(password)

    @property
    def imap_password(self) -> str:
        """The IMAP password in clear text, for logging in."""
        return decrypt_secret(self.imap_password_encrypted)

    @property
    def smtp_password(self) -> str:
        """The SMTP password: the IMAP password with "same access data" (EML-035), else its own."""
        if self.smtp_same_login:
            return self.imap_password
        return decrypt_secret(self.smtp_password_encrypted) if self.smtp_password_encrypted else ""

    @property
    def smtp_login(self) -> str:
        """The SMTP user: the IMAP user with "same access data" (EML-035); empty means no login."""
        return self.imap_user if self.smtp_same_login else self.smtp_user

    @property
    def can_fetch(self) -> bool:
        """Whether everything needed for fetching is filled in."""
        return bool(self.is_active and self.imap_host and self.imap_user and self.imap_password_encrypted)

    @property
    def can_send(self) -> bool:
        """Whether everything needed for sending is filled in."""
        return bool(self.is_active and self.smtp_host and self.address)

    @property
    def delete_after_import(self) -> bool:
        """Whether assigned mails are deleted from the server (EML-006); the legacy name."""
        return self.after_assignment == AfterAssignment.DELETE

    @property
    def password_readable(self) -> bool:
        """Whether the stored passwords can be decrypted; not after ``secret_key`` was changed (EML-002)."""
        try:
            for secret in (self.imap_password_encrypted, self.smtp_password_encrypted):
                decrypt_secret(secret)
        except SecretUnreadableError:
            return False
        return True

    def clean(self) -> None:
        """Only a correspondence mailbox sends the correspondence; moving needs a folder other than the inbox."""
        super().clean()
        errors = {}
        if self.is_outgoing and not self.for_correspondence:
            errors["is_outgoing"] = _("Only a mailbox for correspondence can send the mails of the projects.")
        # The folder matters only where mails are fetched.
        if self.for_correspondence and self.after_assignment == AfterAssignment.MOVE:
            if not self.done_folder.strip():
                errors["done_folder"] = _("Name the folder the assigned mails are moved into.")
            elif self.done_folder.strip().lower() == self.inbox_folder.strip().lower():
                # Moving into the inbox would fetch the mail again.
                errors["done_folder"] = _("Choose a folder other than the inbox.")
        if errors:
            raise ValidationError(errors)


class MailboxAddress(AuditedModel):
    """A further address (alias) that delivers into a mailbox, e.g. ``support@`` and ``projekt@`` (EML-047).

    Which address a mail went to is read from ``Delivered-To``,
    ``X-Original-To``, ``To`` and ``Cc`` (``mail.aliases.address_of``).
    Per address:

    * ``untagged`` – what becomes of a mail **without** project tag: left
      alone, taken in as an inquiry, or turned into a service case at once
      (with ``case_manager`` responsible for it). Tagged mails and replies
      are assigned as always.
    * ``for_service_cases`` – the role "only for service cases": mails written
      in a service case go out with this address as sender. At most one
      address has it (``mail.aliases.save_address``).

    The mailbox's own address keeps the mailbox's ``process_untagged`` unless
    it is listed here itself.

    EML-049: ``untagged_since`` and ``untagged_unread_only`` as for the
    mailbox, for the mails without tag this address takes in.

    EML-052: ``sender_roles`` – the roles whose members may choose
    this address as sender of a project mail; it goes out through the SMTP
    server of its mailbox (``mail.senders``).
    """

    mailbox = models.ForeignKey(Mailbox, verbose_name=_("mailbox"), on_delete=models.CASCADE, related_name="aliases")
    address = models.EmailField(_("address"))
    untagged = models.CharField(
        _("mails without project tag"),
        max_length=12,
        choices=Untagged.choices,
        default=Untagged.INQUIRY,
        help_text=_("Mails with a project tag and replies to assigned mails go to their project in any case."),
    )
    # EML-049: as for the mailbox – mails without tag only from a point in time, optionally only unread.
    untagged_since = models.DateTimeField(
        _("taken in from"),
        null=True,
        blank=True,
        help_text=_(
            "Only mails that arrived in the mailbox from this moment on are taken in; older ones stay in the "
            "inbox untouched. Set to the moment of switching on; empty means now."
        ),
    )
    untagged_unread_only = models.BooleanField(
        _("only unread mails"),
        default=False,
        help_text=_("Mails already read in the mailbox stay in the inbox untouched."),
    )
    for_service_cases = models.BooleanField(
        _("only for service cases"),
        default=False,
        help_text=_(
            "Mails written in a service case go out with this address as sender. Only one address can have this role."
        ),
    )
    case_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("responsible for new service cases"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=_("Gets the service cases made from mails to this address, and a notification."),
    )
    # EML-052: who may choose this address as sender of a mail written in a project.
    sender_roles = models.ManyToManyField(
        "accounts.Role",
        verbose_name=_("may send from this address"),
        blank=True,
        related_name="+",
        help_text=_(
            "Members of these roles may choose this address as sender of a mail written in a project. "
            "Superusers may use every address."
        ),
    )

    class Meta:
        verbose_name = _("address of a mailbox")
        verbose_name_plural = _("addresses of mailboxes")
        ordering = ["address", "id"]
        constraints = [models.UniqueConstraint(fields=["mailbox", "address"], name="mail_alias_unique_address")]

    def __str__(self) -> str:
        return self.address

    def audit_parent(self) -> models.Model | None:
        """Show changes of the addresses in the history of the mailbox."""
        return self.mailbox

    def clean(self) -> None:
        """Addresses are compared in lower case."""
        super().clean()
        self.address = (self.address or "").strip().lower()


def keep_mailbox_name(record: Any, save_options: dict[str, Any]) -> None:
    """Note the name of the mailbox on a mail or log entry that is saved (EML-046).

    A mailbox can be deleted; the mails and the mail log then still name it
    by this copy. It follows a renamed mailbox (``mail.mailboxes.save_mailbox``)
    and is kept as it was when the mailbox goes.
    """
    if record.mailbox_id is None or record.mailbox_name:
        return
    record.mailbox_name = record.mailbox.name[:120]
    fields = save_options.get("update_fields")
    if fields is not None and "mailbox_name" not in fields:
        save_options["update_fields"] = [*fields, "mailbox_name"]


def mailbox_label(record: Any) -> str:
    """The mailbox of a mail or log entry as shown: its name, "(deleted)" once it is gone (EML-046)."""
    if record.mailbox_id is not None:
        return record.mailbox_name or str(record.mailbox)
    if record.mailbox_name:
        return _("%(name)s (deleted)") % {"name": record.mailbox_name}
    return ""


class CrewAnswerMode(models.TextChoices):
    """How the people answer a deployment request (PER-016, PER-032).

    By reply mail the request mail carries the buttons "Accept" and
    "Decline": ``mailto:`` links to a mailbox Rentalars fetches, so that the
    server need not be reachable from the internet (``mail.crew_answers``).
    """

    LINK = "link", _("by the link in the browser")
    MAIL = "mail", _("by reply mail")
    BOTH = "both", _("both")


class MailSettings(SingletonModel):
    """What holds for all mailboxes (EML-005, EML-028, EML-031, EML-034, EML-038).

    The mailboxes themselves – access, folders, state of the fetch – are
    :class:`Mailbox` rows (EML-041).

    PER-032: ``crew_answers`` – whether deployment requests are
    answered by the link, by reply mail or both. "Both" is the default: with
    a mailbox that Rentalars fetches the request carries the buttons and the
    link, without one only the link (``mail.crew_answers.answer_mailbox``).

    EML-055: ``lock_new_in_projects`` and ``lock_new_in_cases`` – whether
    new messages of a project, of a service case start with the lock.
    """

    # EML-038: mails written in Rentalars name the writer and the company as sender; this
    # name is only the fallback for a mail without a known writer.
    sender_name = models.CharField(
        _("sender name"),
        max_length=120,
        blank=True,
        help_text=_("Only for mails without a known writer; otherwise the sender is “name | company”."),
    )

    # EML-034: one signature for everybody, with placeholders for the data of the writer.
    signature_html = models.TextField(_("signature"), blank=True)

    interval_minutes = models.PositiveSmallIntegerField(
        _("fetch every … minutes"), default=2, validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    max_message_mb = models.PositiveSmallIntegerField(
        _("largest mail (MB)"),
        default=25,
        validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text=_("Attachments of larger mails are left in the mailbox."),
    )
    retention_days = models.PositiveIntegerField(
        _("keep mails for … days"),
        default=0,
        help_text=_("0: keep. Otherwise older mails are deleted from Rentalars every night."),
    )
    # PER-032: answering a deployment request by reply mail, for a server that is not reachable from the internet.
    crew_answers = models.CharField(
        _("answer to deployment requests"),
        max_length=8,
        choices=CrewAnswerMode.choices,
        default=CrewAnswerMode.BOTH,
        help_text=_(
            "By reply mail, the request carries the buttons “Accept” and “Decline”. They open a prepared mail "
            "to a mailbox that Rentalars fetches – the answer needs no access to Rentalars. Choose it when the "
            "server cannot be reached from the internet: then the link in the request leads nowhere outside. "
            "Without a mailbox that is fetched, the request carries only the link."
        ),
    )

    # S2: the name of the own mail server in the ``Authentication-Results`` headers. Set, an answer by mail
    # counts only if that server wrote ``dmarc=pass`` (or ``dkim=pass`` for the domain of the sender).
    crew_answer_trusted_server = models.CharField(
        _("name of your mail server in the check results"),
        max_length=120,
        blank=True,
        help_text=_(
            "The word before the first semicolon in the header “Authentication-Results” of your mail server, e.g. "
            "mx.example.com. Filled in, an answer by mail counts only if this server confirmed the sender (DMARC or "
            "DKIM). Empty: only the address of the sender is compared – anybody who knows it can write it."
        ),
    )

    # EML-055: how new messages start – received, written, noted, taken over (``mail.locks.default_lock``).
    # Correspondence in projects is always confidential, in service cases normally not.
    lock_new_in_projects = models.BooleanField(
        _("new messages in projects: with lock"),
        default=True,
        help_text=_("Only those who may see prices and calculation read them until the lock is taken off."),
    )
    lock_new_in_cases = models.BooleanField(
        _("new messages in service cases: with lock"),
        default=False,
        help_text=_("Without lock, whoever works on the service case reads them, also without the price right."),
    )

    class Meta:
        verbose_name = _("mail settings")
        verbose_name_plural = _("mail settings")

    def __str__(self) -> str:
        return str(_("Mail settings"))

    @property
    def max_message_bytes(self) -> int:
        """The size limit of a mail in bytes (EML-028)."""
        return int(self.max_message_mb) * 1024 * 1024

    def clean(self) -> None:
        """L9: the name of the mail server is one word – what stands before the first semicolon."""
        super().clean()
        if self.pk and self.crew_answer_trusted_server == (
            type(self).objects.filter(pk=self.pk).values_list("crew_answer_trusted_server", flat=True).first()
        ):
            # What was stored earlier is not ours to refuse: whoever saves other settings must not be stopped by it. The
            # self-test says when the name never fits; a changed value is checked.
            return
        name = (self.crew_answer_trusted_server or "").strip()
        if name and (any(character.isspace() or character in ";()\"'" for character in name) or "@" in name):
            raise ValidationError(
                {
                    "crew_answer_trusted_server": _(
                        "Enter the name only, e.g. mx.example.com: one word, without spaces, semicolon or quotation "
                        "marks – the word before the first semicolon in “Authentication-Results”."
                    )
                }
            )
        self.crew_answer_trusted_server = name


def message_key(message_id: str) -> str:
    """A fixed-length key of a Message-ID, for finding a mail again (EML-007, EML-012).

    Message-IDs may be up to 998 characters long; the key is its SHA-256.
    Angle brackets, spaces and case are ignored, as mail programs differ there.
    """
    normalized = message_id.strip().strip("<>").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8", "replace")).hexdigest()


class Direction(models.TextChoices):
    """Received or sent – or a note written into the correspondence (EML-051)."""

    INCOMING = "in", _("received")
    OUTGOING = "out", _("sent")
    #: EML-051: no mail – a phone call, a talk, an agreement, noted with its time in the chronology.
    NOTE = "note", _("note")


#: The mail log knows mails only: received and sent.
LOG_DIRECTIONS = [
    (Direction.INCOMING.value, Direction.INCOMING.label),
    (Direction.OUTGOING.value, Direction.OUTGOING.label),
]


class MailKind(models.TextChoices):
    """What kind of mail it is (EML-030)."""

    NORMAL = "", _("mail")
    AUTO_REPLY = "auto_reply", _("automatic reply")
    BOUNCE = "bounce", _("delivery failure")


class AssignedBy(models.TextChoices):
    """How the mail came to its project (EML-008, EML-012, EML-015)."""

    TAG = "tag", _("by the tag in the subject")
    REFERENCE = "reference", _("as a reply to an assigned mail")
    MANUAL = "manual", _("by hand")
    SENT = "sent", _("sent from the project")
    #: EML-051: a note written in the correspondence.
    NOTE = "note", _("written as a note")
    #: EML-047: a mail without tag to an address that makes a service case of it at once.
    NEW_CASE = "new_case", _("as a new service case")


class ProjectMail(AuditedModel):
    """A mail of a project, received or sent (EML-019, EML-024) – or a note (EML-051).

    A note (``direction`` "note", ``mail.notes``) is no mail: somebody wrote
    down a phone call, a talk or an agreement with the time it happened, so
    that it stands in the chronology of the correspondence. ``sent_by`` is who
    wrote it; it has no addresses, no Message-ID, no attachments and cannot be
    answered.

    The assignment can be changed afterwards; the change of ``project`` is
    recorded in the change log (EML-015). Texts and addresses are kept out
    of that log – they stay in the mail itself.

    EML-055 (EML-029): ``locked`` – a message "with lock" is read only by
    those who may read the correspondence and see prices; an open one also by
    the crew planned in the project (``mail.locks``). New and incoming
    messages start as the mail settings say – in projects with lock, in
    service cases open (``MailSettings.lock_new_in_projects``,
    ``lock_new_in_cases``); its attachments follow the message. The field's
    own default (with lock) holds where no code path chose.
    """

    project = models.ForeignKey(
        "projects.Project", verbose_name=_("project"), on_delete=models.CASCADE, related_name="mails"
    )
    direction = models.CharField(_("direction"), max_length=4, choices=Direction.choices, default=Direction.INCOMING)
    kind = models.CharField(_("kind"), max_length=12, choices=MailKind.choices, blank=True, default=MailKind.NORMAL)
    message_key = models.CharField(max_length=64, unique=True, editable=False)
    message_id = models.TextField(_("Message-ID"), editable=False)
    in_reply_to = models.TextField(blank=True, editable=False)
    references = models.TextField(blank=True, editable=False)
    subject = models.CharField(_("subject"), max_length=500, blank=True)
    sender_name = models.CharField(_("sender"), max_length=200, blank=True)
    sender_address = models.CharField(_("sender address"), max_length=254, blank=True)
    to_addresses = models.TextField(_("to"), blank=True)
    cc_addresses = models.TextField(_("copy to"), blank=True)
    # EML-037: only for sent mails; the recipients do not see these addresses.
    bcc_addresses = models.TextField(_("blind copy to"), blank=True)
    date = models.DateTimeField(_("date"), default=timezone.now)
    text_body = models.TextField(_("text"), blank=True)
    html_body = models.TextField(_("text as HTML"), blank=True)
    assigned_by = models.CharField(_("assigned"), max_length=10, choices=AssignedBy.choices, default=AssignedBy.TAG)
    imported_at = models.DateTimeField(_("taken over"), default=timezone.now, editable=False)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("sent by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    project_was_finished = models.BooleanField(
        _("arrived for a finished project"),
        default=False,
        editable=False,
        help_text=_("The project was finished or cancelled when the mail arrived."),
    )
    attachments_note = models.TextField(_("attachments left out"), blank=True)
    size = models.PositiveIntegerField(_("size"), default=0)
    # EML-041: the mailbox the mail came in through or went out through.
    # EML-046: a mailbox can be deleted; the mail then keeps its name (``mailbox_name``).
    mailbox = models.ForeignKey(
        Mailbox,
        verbose_name=_("mailbox"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mails",
        editable=False,
    )
    mailbox_name = models.CharField(_("name of the mailbox"), max_length=120, blank=True, editable=False)
    # PRJ-106: the correspondence with a supplier of subrentals of the project – set by the address when the
    # mail is stored, or by hand (``rentalars.mail.suppliers``).
    supplier = models.ForeignKey(
        "masterdata.Supplier",
        verbose_name=pgettext_lazy("subrental", "supplier"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mails",
    )
    # EML-055 (EML-029): locked – only for who sees prices; open – also for the crew of the project.
    locked = models.BooleanField(
        _("with lock"),
        default=True,
        help_text=_(
            "With lock, only those who may see prices and calculation read the message. Without, the crew "
            "planned in the project reads it as well."
        ),
    )

    audit_exclude = frozenset(
        {
            "mailbox",
            "mailbox_name",
            "message_key",
            "message_id",
            "in_reply_to",
            "references",
            "text_body",
            "html_body",
            "to_addresses",
            "cc_addresses",
            "bcc_addresses",
            "sender_name",
            "sender_address",
            "attachments_note",
            "size",
            "imported_at",
        }
    )

    class Meta:
        verbose_name = _("project mail")
        verbose_name_plural = _("project mails")
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["project", "date"], name="mail_project_date_idx")]

    def __str__(self) -> str:
        return self.subject or str(_("(no subject)"))

    def audit_parent(self) -> models.Model | None:
        """Show assignments in the history of the project."""
        return self.project

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Store the mail with the name of its mailbox (EML-046)."""
        keep_mailbox_name(self, kwargs)
        super().save(*args, **kwargs)

    @property
    def mailbox_label(self) -> str:
        """The mailbox the mail went through; a deleted one by its name, marked as deleted (EML-046)."""
        return mailbox_label(self)

    @property
    def sender_label(self) -> str:
        """Name and address of the sender, as a mail program shows them."""
        if self.sender_name and self.sender_address:
            return f"{self.sender_name} <{self.sender_address}>"
        return self.sender_name or self.sender_address

    @property
    def is_automatic(self) -> bool:
        """Whether it is an automatic reply or a delivery failure (EML-030)."""
        return self.kind != MailKind.NORMAL

    @property
    def is_note(self) -> bool:
        """EML-051: a note written into the correspondence – no mail, nothing to answer."""
        return self.direction == Direction.NOTE

    @property
    def display_subject(self) -> str:
        """The subject as lists show it: of a note its title (EML-051), of a mail its subject."""
        return self.note_title if self.is_note else self.subject

    @property
    def note_title(self) -> str:
        """EML-051: how a note is listed – its subject, else the beginning of its text."""
        if self.subject:
            return self.subject
        first = next((line.strip() for line in self.text_body.splitlines() if line.strip()), "")
        return first if len(first) <= 80 else first[:79].rstrip() + "…"


def attachment_path(instance: MailAttachment, filename: str) -> str:
    """Store attachments under a random name in a folder per project (as project files)."""
    extension = Path(filename).suffix.lower()[:10]
    return f"mail/{instance.mail.project_id}/{secrets.token_hex(12)}{extension}"


class MailAttachment(models.Model):
    """An attachment of a project mail (EML-020, EML-028)."""

    mail = models.ForeignKey(ProjectMail, verbose_name=_("mail"), on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(_("file"), upload_to=attachment_path, max_length=200)
    filename = models.CharField(_("file name"), max_length=255)
    content_type = models.CharField(_("type"), max_length=120, blank=True)
    size = models.PositiveBigIntegerField(_("size"), default=0)
    content_id = models.CharField(max_length=255, blank=True, help_text=_("For pictures shown inside the text."))
    is_inline = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")
        ordering = ["id"]

    def __str__(self) -> str:
        return self.filename


class InquirySource(models.TextChoices):
    """Where an entry under Projekte → Anfragen comes from (EML-053)."""

    #: Taken in by Rentalars: a mail from a mailbox, or a defect report an automation put there.
    TAKEN_IN = "", _("taken in by Rentalars")
    #: Noted by hand, e.g. during a phone call.
    MANUAL = "manual", _("noted by hand")


class UnknownTagMail(models.Model):
    """A mail waiting under Projects → Inquiries to be taken over by hand (EML-014, EML-042).

    Also a defect report an automation put there (MAT-057,
    ``defect_report``): it becomes a service case or is taken off the list –
    there is no mail to fetch.

    Either its tag names no project (``tag`` holds the number), or it has no
    tag at all and came into a mailbox that takes such mails in – an inquiry
    (``tag`` is empty, EML-041). The mail itself stays untouched in the inbox
    of its mailbox; only what is needed to show and find it again is noted
    here.

    EML-053: an inquiry noted by hand (``source`` "manual") – a phone
    call written down for the office. It has no mailbox and no mail; its
    ``message_key`` is ``manual:<uuid>``, ``date`` is when the call came in,
    ``sender`` shows who called, and ``contact_name``, ``contact_email``,
    ``phone``, ``customer`` and ``note`` hold what was noted, ``created_by``
    who noted it. Taken over, it becomes a note in the correspondence of the
    project (``mail.inquiries.take_manual_into``); it never starts the
    automations of incoming mails. ``version`` counts its changes for the page
    that follows changes (UIX-020).
    """

    message_key = models.CharField(max_length=64, unique=True)
    message_id = models.TextField(blank=True)
    uid = models.BigIntegerField(default=0)
    subject = models.CharField(_("subject"), max_length=500, blank=True)
    sender = models.CharField(_("sender"), max_length=300, blank=True)
    date = models.DateTimeField(_("date"), null=True, blank=True)
    tag = models.CharField(_("tag"), max_length=120, blank=True)
    #: EML-047: the address of the mailbox the mail went to – a listed alias, else the mailbox's own
    #: address; empty for mails noted earlier.
    address = models.CharField(_("to address"), max_length=254, blank=True)
    first_seen_at = models.DateTimeField(_("found"), default=timezone.now)
    resolved_at = models.DateTimeField(_("dealt with"), null=True, blank=True)
    # EML-041: the mailbox the mail waits in; taking it over fetches it from there.
    mailbox = models.ForeignKey(
        Mailbox,
        verbose_name=_("mailbox"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="waiting_mails",
    )
    # ADM-013, MAT-057: an inquiry made by an automation of a defect report – no mail, nothing in an inbox.
    defect_report = models.OneToOneField(
        "material.DefectReport",
        verbose_name=_("defect report"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="inquiry",
    )
    # --- EML-053: an inquiry noted by hand ----------------------------------------------------
    source = models.CharField(
        _("source"), max_length=10, choices=InquirySource.choices, blank=True, default=InquirySource.TAKEN_IN
    )
    contact_name = models.CharField(_("who"), max_length=200, blank=True)
    contact_email = models.EmailField(_("e-mail address"), blank=True)
    phone = models.CharField(_("phone"), max_length=60, blank=True)
    customer = models.ForeignKey(
        "customers.Customer",
        verbose_name=_("customer"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    note = models.TextField(_("note"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("noted by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    version = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = _("inquiry or mail with unknown tag")
        verbose_name_plural = _("inquiries and mails with unknown tag")
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return f"{self.tag} {self.subject}".strip()

    @property
    def is_inquiry(self) -> bool:
        """Whether the mail came without any tag (EML-041) – or the inquiry was noted by hand (EML-053)."""
        return not self.tag

    @property
    def is_defect(self) -> bool:
        """MAT-057: an inquiry made of a defect report – not a mail."""
        return self.defect_report_id is not None

    @property
    def is_manual(self) -> bool:
        """EML-053: an inquiry noted by hand – not a mail, nothing to fetch."""
        return self.source == InquirySource.MANUAL


class LogKind(models.TextChoices):
    """Which way a mail took (EML-039)."""

    PROJECT = "project", _("project mail")
    SYSTEM = "system", _("system mail")
    #: ADM-013: the answer of an automation to a mail without project tag.
    AUTOMATIC = "automatic", _("automatic answer")


class LogResult(models.TextChoices):
    """What became of a mail (EML-039)."""

    ASSIGNED = "assigned", _("assigned")
    UNKNOWN_TAG = "unknown_tag", _("unknown tag")
    # EML-041: a mail without tag, taken in by a mailbox that processes such mails.
    INQUIRY = "inquiry", _("inquiry")
    LEFT_IN_INBOX = "left", _("left in the inbox")
    SENT = "sent", _("sent")
    FAILED = "failed", _("failed")
    #: EML-048: a system mail while no mail server is set up – it only went to the server's log.
    NOT_SENT = "not_sent", _("not sent – no mail server set up")
    # PER-032: an answer to a deployment request by reply mail; ``detail`` says which (CREW_ANSWER_DETAILS).
    CREW_ANSWER = "crew_answer", _("answer to a deployment request")


#: PER-032: the ``detail`` of a log entry for an answer by mail – ``accepted`` or ``declined``, and for
#: an answer that was not taken over the reason behind a colon, e.g. ``accepted:answered``.
CREW_ANSWER_DETAILS = {
    "accepted": _("acceptance"),
    "declined": _("refusal"),
}
CREW_ANSWER_REASONS = {
    "answered": _("not taken over: answered already"),
    "expired": _("not taken over: the deployment is over"),
    "withdrawn": _("not taken over: the request no longer holds"),
    "replaced": _("not taken over: a newer request was sent"),
    "cancelled": _("not taken over: the project was cancelled or closed"),
    # PER-032: the answer did not come from the address the request went to, or it looks forged.
    "sender": _("not taken over: it did not come from the address the request was sent to"),
    "forged": _("not taken over: the check of the sender failed"),
    # S2: the mail server named in the settings did not confirm the sender.
    "unconfirmed": _("not taken over: the mail server did not confirm the sender"),
}


#: EML-049: why a mail without tag was left in the inbox although its address takes such mails in.
#: The ``detail`` of such a log entry is the reason, or the reason and the listed address behind a colon,
#: e.g. ``before_cutoff:support@example.org``.
LEFT_REASONS = {
    "before_cutoff": _("arrived before the moment from which mails without tag are taken in"),
    "read": _("already read – only unread mails without tag are taken in"),
}


class MailLogEntry(models.Model):
    """One mail that came in or went out (EML-039).

    Project mails: every mail the fetch looked at – assigned, with an unknown
    tag, or left in the inbox – and every mail sent from a project.
    System mails: everything Django sends (invitations, password links,
    notifications), noted by ``mail.backends.LoggingEmailBackend``.

    Only the envelope is kept, never the text. Entries are removed after the
    retention period of the mails, or after 365 days if mails are kept
    (``mail.log.delete_old_entries``).
    """

    timestamp = models.DateTimeField(_("time"), default=timezone.now, db_index=True)
    direction = models.CharField(_("direction"), max_length=3, choices=LOG_DIRECTIONS)
    kind = models.CharField(_("kind"), max_length=10, choices=LogKind.choices)
    result = models.CharField(_("result"), max_length=12, choices=LogResult.choices)
    sender = models.CharField(_("sender"), max_length=300, blank=True)
    recipients = models.TextField(_("recipients"), blank=True)
    subject = models.CharField(_("subject"), max_length=500, blank=True)
    project = models.ForeignKey(
        "projects.Project",
        verbose_name=_("project"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    mail = models.ForeignKey(
        ProjectMail, verbose_name=_("mail"), null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("sent by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    message_key = models.CharField(max_length=64, blank=True, db_index=True)
    detail = models.TextField(_("detail"), blank=True, help_text=_("The error, or a note such as the unknown tag."))
    # EML-041: the mailbox the mail went through; empty for system mails sent through the configuration.
    # EML-046: a mailbox can be deleted; the entry then keeps its name (``mailbox_name``).
    mailbox = models.ForeignKey(
        Mailbox,
        verbose_name=_("mailbox"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="log_entries",
    )
    mailbox_name = models.CharField(_("name of the mailbox"), max_length=120, blank=True)

    class Meta:
        verbose_name = _("mail log entry")
        verbose_name_plural = _("mail log")
        ordering = ["-timestamp", "-id"]

    def __str__(self) -> str:
        return f"{self.get_direction_display()} {self.subject}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Store the entry with the name of its mailbox (EML-046)."""
        keep_mailbox_name(self, kwargs)
        super().save(*args, **kwargs)

    @property
    def mailbox_label(self) -> str:
        """The mailbox the mail went through; a deleted one by its name, marked as deleted (EML-046)."""
        return mailbox_label(self)

    @property
    def detail_text(self) -> str:
        """The detail as shown: how an assigned mail was assigned, else the stored text."""
        if self.result == LogResult.ASSIGNED and self.detail in AssignedBy.values:
            return str(AssignedBy(self.detail).label)
        if self.result == LogResult.CREW_ANSWER:
            # PER-032: "acceptance", or "refusal – not taken over: answered already".
            answer, _colon, reason = self.detail.partition(":")
            label = str(CREW_ANSWER_DETAILS.get(answer, answer))
            return f"{label} – {CREW_ANSWER_REASONS.get(reason, reason)}" if reason else label
        if self.result == LogResult.LEFT_IN_INBOX:
            # EML-049: "arrived before the moment … (support@…)"; older entries have only the address.
            reason, _colon, address = self.detail.partition(":")
            if reason in LEFT_REASONS:
                text = str(LEFT_REASONS[reason])
                return f"{text} ({address})" if address else text
        return self.detail


class CrewRequestMail(models.Model):
    """A deployment request that went out by mail and can be answered by reply mail (PER-032).

    The buttons of the request mail open a mail whose subject ends with
    ``[RA-E-<token>-JA]`` or ``[RA-E-<token>-NEIN]`` (``mail.crew_answers``).
    The token is random and cannot be guessed; it stands for one request to
    one person. ``requested_at`` is the time of that request: asking again
    or planning somebody else on the line makes an answer to this token one
    to a request that no longer holds. The line and the person are kept as
    ``NULL`` when they are deleted, so that a late answer can still be told
    so.
    """

    token = models.CharField(max_length=32, unique=True, editable=False)
    #: PER-032: the address the request mail went to – only a mail from this address is an answer, so that
    #: a forwarded request cannot be answered by its new holder. Empty for requests sent earlier.
    sent_to = models.CharField(_("sent to"), max_length=254, blank=True, editable=False)
    line = models.ForeignKey(
        "projects.CrewLine",
        verbose_name=_("crew line"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    person = models.ForeignKey(
        "personnel.Person",
        verbose_name=_("person"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    requested_at = models.DateTimeField(_("asked at"))
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    answered_at = models.DateTimeField(_("answered at"), null=True, blank=True)

    class Meta:
        verbose_name = _("deployment request by mail")
        verbose_name_plural = _("deployment requests by mail")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.token
