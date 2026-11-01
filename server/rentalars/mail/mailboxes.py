# SPDX-License-Identifier: GPL-3.0-or-later
"""The mailboxes and their roles (EML-041, EML-003, EML-002, EML-035).

Rentalars works with any number of existing mailboxes. Each has roles:

* **Correspondence** – new mails are fetched and assigned to projects by
  their tag (``mail.fetching``). Several mailboxes may have this role.
* **Outgoing correspondence** – exactly one of the active correspondence
  mailboxes sends the mails written in projects (``mail.sending``); its
  address is the sender.
* **System** – at most one mailbox sends the system mails: invitations,
  password links, notifications (``mail.backends``). Without one they go
  through ``[email]`` of the configuration file.

The rules are kept by :func:`save_mailbox`: giving "outgoing" or "system"
to a mailbox takes the role from the mailbox that had it, and a change that
would leave active correspondence mailboxes without the one that sends is
refused.

EML-046: every mailbox can be deleted (:func:`delete_mailbox`) –
also one through which mails came in or went out. The stored mails and the
mail log keep its name (``mailbox_name``); what waited in it under
Projects → Inquiries leaves the list, and its roles go with it. Before,
such a mailbox was only switched off; switching off stays possible
(:func:`switch_off_mailbox`). What deleting will do is told beforehand
(:func:`deletion_of`).

Browser views and API call these functions alike (API-002).
"""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import formataddr, parseaddr
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import QuerySet
from django.utils.translation import gettext as _

from rentalars.core.crypto import SecretUnreadableError
from rentalars.mail.aliases import stamp_untagged_since
from rentalars.mail.imap import MailboxError
from rentalars.mail.models import Mailbox, MailLogEntry, ProjectMail, Security

#: Seconds to wait for the mail server before giving up.
TIMEOUT = 30


# --- Who does what ------------------------------------------------------------------------------


def correspondence_mailboxes() -> QuerySet[Mailbox]:
    """The active mailboxes of the correspondence: fetched and assigned (EML-041)."""
    return Mailbox.objects.filter(is_active=True, for_correspondence=True)


def outgoing_mailbox() -> Mailbox | None:
    """The mailbox that sends the mails written in projects, if one is active (EML-041)."""
    return Mailbox.objects.filter(is_active=True, for_correspondence=True, is_outgoing=True).first()


def can_send_correspondence() -> bool:
    """Whether mails can be written in projects: the outgoing mailbox is complete (EML-024, EML-041)."""
    mailbox = outgoing_mailbox()
    return mailbox is not None and mailbox.can_send


def can_send_from(project: Any) -> bool:
    """Whether a mail of this project can go out (EML-024, EML-047, EML-050).

    A service case may send through the mailbox of its own address when the
    general outgoing mailbox is missing; every other project needs that one.
    The panel of a service case and the tab "Korrespondenz" ask this alike.
    """
    from rentalars.mail.aliases import sender_for

    mailbox, _address = sender_for(project)
    return mailbox is not None and mailbox.can_send


def system_mailbox() -> Mailbox | None:
    """The active mailbox that sends the system mails, if one is set up completely (EML-041)."""
    mailbox = Mailbox.objects.filter(is_active=True, for_system=True).first()
    return mailbox if mailbox is not None and mailbox.can_send else None


def own_addresses() -> set[str]:
    """The addresses of all mailboxes, in lower case: never recipients of an answer to all (EML-037).

    EML-047: with the further addresses (aliases) of the mailboxes.
    """
    from rentalars.mail.models import MailboxAddress

    addresses = {address.lower() for address in Mailbox.objects.exclude(address="").values_list("address", flat=True)}
    return addresses | {address.lower() for address in MailboxAddress.objects.values_list("address", flat=True)}


def legacy_mailbox() -> Mailbox | None:
    """The mailbox the older settings meant: the one that sends, else the first of the correspondence."""
    return (
        Mailbox.objects.filter(is_outgoing=True).first()
        or Mailbox.objects.filter(for_correspondence=True).order_by("id").first()
    )


# --- Changing ------------------------------------------------------------------------------------

#: The roles a single mailbox carries: field name and the note when another mailbox takes it.
_SINGLE_ROLES = (
    ("is_outgoing", lambda name: _("%(mailbox)s no longer sends the correspondence.") % {"mailbox": name}),
    ("for_system", lambda name: _("%(mailbox)s no longer sends the system mails.") % {"mailbox": name}),
)


def _check_data(mailbox: Mailbox) -> None:
    """What an active mailbox needs for its roles (EML-002, EML-035)."""
    if not mailbox.is_active:
        return
    errors: dict[str, str] = {}
    if mailbox.for_correspondence:
        if not (mailbox.imap_host and mailbox.imap_user):
            raise ValidationError(_("Fill in the IMAP server and user before switching the mailbox on."))
        if not mailbox.imap_password_encrypted:
            errors["imap_password"] = _("Enter the password of the mailbox.")
    if mailbox.is_outgoing or mailbox.for_system:
        if not mailbox.smtp_host:
            errors["smtp_host"] = _("A mailbox that sends needs the SMTP server.")
        if not mailbox.address:
            errors["address"] = _("A mailbox that sends needs its address.")
    if not mailbox.smtp_same_login and mailbox.smtp_user and not mailbox.smtp_password_encrypted:
        errors["smtp_password"] = _("Enter the password for sending.")
    if errors:
        raise ValidationError(errors)


def _check_roles(*, field: str | None = "is_outgoing") -> None:
    """Exactly one active correspondence mailbox sends, if there is any (EML-041).

    Raises:
        ValidationError: The rule does not hold; on ``field`` if given.
    """
    correspondence = correspondence_mailboxes()
    if correspondence.exists() and correspondence.filter(is_outgoing=True).count() != 1:
        message = _(
            "Exactly one active mailbox of the correspondence sends the mails written in projects. "
            "Mark it with “sends the correspondence”."
        )
        raise ValidationError({field: message} if field else message)
    if Mailbox.objects.filter(for_system=True, is_active=True).count() > 1:
        raise ValidationError(_("Only one mailbox can send the system mails."))


@transaction.atomic
def save_mailbox(mailbox: Mailbox, *, imap_password: str = "", smtp_password: str = "") -> list[str]:
    """Store a mailbox; a password is changed only if a new one is given (EML-002, EML-041).

    With "same user and password as for receiving" (EML-035) an SMTP user and
    password of their own are not needed and are removed: no secret is kept
    that nothing uses.

    A mailbox that is marked to send the correspondence or the system mails
    takes that role from the mailbox that had it.

    EML-049: switching on "take in mails without project tag" sets the point
    in time from which they are taken in to now, unless one is given.

    Returns:
        Notes on other mailboxes that gave up a role, for the page.

    Raises:
        ValidationError: Data needed for a role is missing, or the roles do not
            fit together any more.
    """
    if imap_password:
        mailbox.set_imap_password(imap_password)
    if mailbox.smtp_same_login:
        mailbox.smtp_user = ""
        mailbox.smtp_password_encrypted = ""
    elif smtp_password:
        mailbox.set_smtp_password(smtp_password)
    _check_data(mailbox)
    stamp_untagged_since(mailbox)  # EML-049: mails without tag only from the moment of switching on
    mailbox.full_clean()
    notes = []
    others = Mailbox.objects.select_for_update().exclude(pk=mailbox.pk)
    for role, note in _SINGLE_ROLES:
        if not getattr(mailbox, role):
            continue
        for other in others.filter(**{role: True}):
            setattr(other, role, False)
            other.save(update_fields=[role])
            notes.append(note(other))
    renamed = mailbox.pk is not None and Mailbox.objects.filter(pk=mailbox.pk).exclude(name=mailbox.name).exists()
    mailbox.save()
    if renamed:
        _keep_name(mailbox)
    _check_roles()
    return notes


def _keep_name(mailbox: Mailbox) -> None:
    """Write the current name of a mailbox onto its mails and log entries (EML-046)."""
    name = mailbox.name[:120]
    ProjectMail.objects.filter(mailbox=mailbox).exclude(mailbox_name=name).update(mailbox_name=name)
    MailLogEntry.objects.filter(mailbox=mailbox).exclude(mailbox_name=name).update(mailbox_name=name)


@dataclass(frozen=True)
class Deletion:
    """What deleting a mailbox does, told before it is done (EML-046).

    Attributes:
        mails: Project mails that came in or went out through it; they stay.
        log_entries: Entries of the mail log that name it; they stay.
        waiting: Mails waiting in it under Projects → Inquiries; they leave
            the list and stay in the mailbox on the server.
        roles: The roles it has; no mailbox has them afterwards, but for
            sending the correspondence (see ``successors``).
        takes_crew_answers: Answers to deployment requests by mail go to it
            (PER-032); afterwards to another mailbox, or the requests carry only
            the link.
        successors: It sends the correspondence while other mailboxes of the
            correspondence stay active: one of these must take that over.
            Empty when that is not needed.
        blocked: Why it cannot be deleted now, else empty.
    """

    mails: int
    log_entries: int
    waiting: int
    roles: list[str]
    takes_crew_answers: bool
    successors: list[Mailbox]
    blocked: str

    @property
    def needs_successor(self) -> bool:
        """Whether another mailbox has to take over sending the correspondence."""
        return bool(self.successors)


def _successors(mailbox: Mailbox) -> tuple[list[Mailbox], str]:
    """The mailboxes that can send the correspondence instead of this one, and why none can (EML-046)."""
    if not (mailbox.is_active and mailbox.is_outgoing):
        return [], ""
    others = list(correspondence_mailboxes().exclude(pk=mailbox.pk))
    if not others:
        return [], ""
    able = [other for other in others if other.can_send]
    if able:
        return able, ""
    return [], _(
        "This mailbox sends the correspondence, and no other active mailbox of the correspondence can send: "
        "enter the SMTP server and the address of one of them first, or switch them off."
    )


def deletion_of(mailbox: Mailbox) -> Deletion:
    """What deleting this mailbox would do, for the confirmation (EML-046)."""
    from rentalars.mail.crew_answers import answer_mailbox
    from rentalars.mail.models import UnknownTagMail

    roles = []
    if mailbox.for_correspondence:
        roles.append(_("correspondence"))
    if mailbox.is_outgoing:
        roles.append(_("sends the correspondence"))
    if mailbox.for_system:
        roles.append(_("system mails"))
    answers = answer_mailbox()
    successors, blocked = _successors(mailbox)
    return Deletion(
        mails=mailbox.mails.count(),
        log_entries=mailbox.log_entries.count(),
        waiting=UnknownTagMail.objects.filter(mailbox=mailbox, resolved_at__isnull=True).count(),
        roles=roles,
        takes_crew_answers=answers is not None and answers.pk == mailbox.pk,
        successors=successors,
        blocked=blocked,
    )


@transaction.atomic
def delete_mailbox(mailbox: Mailbox, *, successor: Mailbox | None = None) -> list[str]:
    """Delete a mailbox, also one through which mails came in or went out (EML-046).

    The mails and the mail log keep its name; mails waiting in it under
    Projects → Inquiries leave the list (they stay on the server). No mailbox
    has its roles afterwards – system mails then go through the configuration
    of the server – except sending the correspondence while other mailboxes
    of the correspondence stay active: ``successor`` takes that over. It may
    be left out when only one other mailbox can do it.

    Args:
        mailbox: The mailbox to delete.
        successor: The mailbox that sends the correspondence from now on.

    Returns:
        Notes for the page, e.g. which mailbox sends the correspondence now.

    Raises:
        ValidationError: Another mailbox must take over sending the
            correspondence, and none or no suitable one is named.
    """
    successors, blocked = _successors(mailbox)
    if blocked:
        raise ValidationError(blocked)
    notes = []
    if successors:
        if successor is None and len(successors) == 1:
            successor = successors[0]
        if successor is None or successor.pk not in {other.pk for other in successors}:
            raise ValidationError(
                {
                    "successor": _("Choose the mailbox that sends the correspondence from now on: %(names)s.")
                    % {"names": ", ".join(f"“{other}”" for other in successors)}
                }
            )
    _keep_name(mailbox)
    mailbox.delete()
    if successor is not None:
        # The role goes over by the rules of saving: its data are checked like when it is given by hand.
        successor.is_outgoing = True
        save_mailbox(successor)
        notes.append(_("“%(mailbox)s” sends the correspondence now.") % {"mailbox": successor})
    _check_roles(field=None)
    return notes


@transaction.atomic
def switch_off_mailbox(mailbox: Mailbox) -> None:
    """Switch a mailbox off instead of deleting it: neither fetched nor used for sending (EML-041, EML-046).

    Raises:
        ValidationError: It sends the correspondence while other mailboxes of
            the correspondence stay active.
    """
    mailbox.is_active = False
    mailbox.save(update_fields=["is_active"])
    _check_roles(field=None)


# --- Connecting -----------------------------------------------------------------------------------


@contextmanager
def smtp_session(mailbox: Mailbox) -> Iterator[smtplib.SMTP]:
    """A connection to the SMTP server of a mailbox – always encrypted, logged in if a user is set (EML-002).

    Errors of the connection and of what is done with it become a
    :class:`~django.core.exceptions.ValidationError` with a readable text.
    """
    # NFA-071: the server a mailbox names is connected to only at a checked address.
    from rentalars.core.network import BlockedAddressError, smtp_client

    context = ssl.create_default_context()
    try:
        if mailbox.smtp_security == Security.SSL:
            server: smtplib.SMTP = smtp_client(use_ssl=True)(
                mailbox.smtp_host, mailbox.smtp_port, context=context, timeout=TIMEOUT
            )
        else:
            server = smtp_client(use_ssl=False)(mailbox.smtp_host, mailbox.smtp_port, timeout=TIMEOUT)
            server.starttls(context=context)
        with server:
            if mailbox.smtp_login:
                server.login(mailbox.smtp_login, mailbox.smtp_password)
            yield server
    except SecretUnreadableError as error:
        raise ValidationError(_("The stored password cannot be read any more. Enter it again.")) from error
    except smtplib.SMTPAuthenticationError as error:
        raise ValidationError(_("The mail server refused the login for sending.")) from error
    except smtplib.SMTPRecipientsRefused as error:
        raise ValidationError(
            _("The mail server refused the recipients: %(addresses)s") % {"addresses": ", ".join(error.recipients)}
        ) from error
    except BlockedAddressError as error:
        raise ValidationError(str(error)) from error
    except (TimeoutError, smtplib.SMTPException, ssl.SSLError, OSError) as error:
        raise ValidationError(_("The mail could not be sent: %(error)s") % {"error": error}) from error


@dataclass(frozen=True)
class ConnectionCheck:
    """The outcome of trying one side of a mailbox: ``IMAP`` or ``SMTP``."""

    part: str
    ok: bool
    text: str


def check_connection(mailbox: Mailbox, *, opener: Callable[[Mailbox], Any] | None = None) -> list[ConnectionCheck]:
    """Log in to the IMAP and the SMTP server of a mailbox, without changing or sending anything (EML-041).

    Args:
        mailbox: The mailbox as stored.
        opener: Opens the IMAP side; the tests pass a mailbox in memory.
    """
    from rentalars.mail import fetching

    results = []
    if mailbox.imap_host:
        try:
            with (opener or fetching.open_mailbox)(mailbox) as box:
                box.select_inbox()
        except SecretUnreadableError:
            results.append(
                ConnectionCheck("IMAP", False, _("The stored password cannot be read any more. Enter it again."))
            )
        except MailboxError as error:
            results.append(ConnectionCheck("IMAP", False, str(error)))
        else:
            results.append(
                ConnectionCheck(
                    "IMAP", True, _("Logged in; the folder “%(folder)s” opens.") % {"folder": mailbox.inbox_folder}
                )
            )
    if mailbox.smtp_host:
        try:
            with smtp_session(mailbox):
                pass
        except ValidationError as error:
            results.append(ConnectionCheck("SMTP", False, " ".join(error.messages)))
        else:
            text = _("Logged in.") if mailbox.smtp_login else _("Connected; the server is used without login.")
            results.append(ConnectionCheck("SMTP", True, text))
    if not results:
        results.append(ConnectionCheck("", False, _("Fill in the IMAP or SMTP server first.")))
    return results


# --- System mails (EML-041) -----------------------------------------------------------------------------


def smtp_backend_options(mailbox: Mailbox) -> dict[str, Any]:
    """The options of Django's SMTP backend for sending system mails through a mailbox."""
    try:
        password = mailbox.smtp_password
    except SecretUnreadableError:
        # The login then fails, and the mail log notes the failure.
        password = ""
    ssl_on = mailbox.smtp_security == Security.SSL
    return {
        "host": mailbox.smtp_host,
        "port": mailbox.smtp_port,
        "username": mailbox.smtp_login,
        "password": password,
        "use_ssl": ssl_on,
        "use_tls": not ssl_on,
        "timeout": TIMEOUT,
    }


#: EML-048: Django's backends that send nothing – they write a mail into the log, a file or nowhere.
LOG_ONLY_BACKENDS = frozenset(
    {
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
        "django.core.mail.backends.filebased.EmailBackend",
    }
)
#: The backend that notes system mails in the mail log and hands them on (``mail.backends``).
_LOGGING_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"


def sending_backend() -> str:
    """The backend that really sends system mails: inside the mail log's wrapper, the configured one (EML-039)."""
    backend = settings.EMAIL_BACKEND
    if backend == _LOGGING_BACKEND:
        backend = getattr(settings, "EMAIL_INNER_BACKEND", "") or "django.core.mail.backends.smtp.EmailBackend"
    return backend


def has_mail_server() -> bool:
    """Whether system mails can go out at all (EML-048).

    They can through a mailbox with the role "system", or through the mail
    server of ``[email]`` in the configuration. Without both, Django's
    console backend only writes them into the log of the server – nothing
    arrives, so nothing counts as sent.
    """
    try:
        if system_mailbox() is not None:
            return True
    except DatabaseError:
        pass  # without the database the configuration alone decides
    return sending_backend() not in LOG_ONLY_BACKENDS


def system_sender(mailbox: Mailbox) -> str:
    """The sender of system mails sent through a mailbox: the name of ``[email]`` with the mailbox's address."""
    name, _address = parseaddr(settings.DEFAULT_FROM_EMAIL)
    return formataddr((name or "Rentalars", mailbox.address))
