# SPDX-License-Identifier: GPL-3.0-or-later
"""An e-mail backend that notes every system mail in the mail log (EML-039).

Django sends invitations, password links, notifications and the test mail
of the self-check through ``settings.EMAIL_BACKEND``. Rentalars sets that to
:class:`LoggingEmailBackend`, which hands every message to the backend that
was configured before – ``settings.EMAIL_INNER_BACKEND``, the SMTP server of
the configuration or the log – and notes the outcome in the mail log::

    EMAIL_INNER_BACKEND = EMAIL_BACKEND
    EMAIL_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"

Sending behaves exactly as without the wrapper: the same connection, the
same errors. Mails of projects do not pass through here; they go out through
the outgoing mailbox of the correspondence and are noted by ``mail.sending``.

EML-041: if a mailbox has the role "system", system mails go out through
its SMTP server instead, with its address as sender (the name of
``DEFAULT_FROM_EMAIL`` stays), and the log names that mailbox. Without such
a mailbox, the configuration (``[email]``) is used as before.

EML-045: on the way, every system mail gets the footer "sent
automatically by Rentalars for <company>: <address>" (``mail.footer``).

EML-048: without a mail server – no mailbox with the role "system"
and no ``host`` in ``[email]``, so that the configured backend only writes
into the log of the server – a mail is still handed on (the log keeps it for
development) but noted as "not sent – no mail server set up" and not counted
as sent: ``send_mail`` returns 0, and the place that sends says so
(``mail.server``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.mail.backends.base import BaseEmailBackend
from django.db import DatabaseError

from rentalars.mail import log
from rentalars.mail.footer import add_footer
from rentalars.mail.mailboxes import LOG_ONLY_BACKENDS, smtp_backend_options, system_mailbox, system_sender
from rentalars.mail.models import Direction, LogKind, LogResult, Mailbox

#: Used when the settings name no inner backend: send by SMTP, as Django would.
DEFAULT_INNER_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
#: The backend for sending through the system mailbox (EML-041).
#: NFA-071: Django's SMTP backend that connects only to a checked address – the mailbox's server was
#: entered in the interface. The server of the configuration file ([email]) is the operator's and keeps
#: Django's own backend.
SMTP_BACKEND = "rentalars.core.network.GuardedSmtpBackend"


def _inner_backend_path() -> str:
    path = getattr(settings, "EMAIL_INNER_BACKEND", "") or DEFAULT_INNER_BACKEND
    # Wrapping itself would recurse for ever.
    return DEFAULT_INNER_BACKEND if path == f"{__name__}.LoggingEmailBackend" else path


def _note(message: EmailMessage, result: str, detail: str = "", mailbox: Mailbox | None = None) -> None:
    log.record(
        direction=Direction.OUTGOING,
        kind=LogKind.SYSTEM,
        result=result,
        sender=message.from_email or settings.DEFAULT_FROM_EMAIL,
        recipients=message.recipients(),
        subject=str(message.subject or ""),
        detail=detail,
        mailbox=mailbox,
    )


class LoggingEmailBackend(BaseEmailBackend):
    """Sends through the configured backend and notes each message in the mail log (EML-039)."""

    def __init__(self, fail_silently: bool = False, **kwargs: Any) -> None:
        """Create the inner backend: the system mailbox if there is one (EML-041), else the configured one.

        Options given by the caller (a server of its own) win over the system mailbox.
        """
        super().__init__(fail_silently=fail_silently)
        self.mailbox: Mailbox | None = None
        # ``send_mail`` always passes ``username=None, password=None``: that is no server of its own.
        if not any(value is not None for value in kwargs.values()):
            try:
                self.mailbox = system_mailbox()
            except DatabaseError:
                # Without the database the configured server still sends, e.g. a report of the problem.
                self.mailbox = None
        #: EML-048: nothing really goes out – the configured backend only writes into the log.
        self.without_server = False
        if self.mailbox is not None:
            self.inner = get_connection(SMTP_BACKEND, fail_silently=fail_silently, **smtp_backend_options(self.mailbox))
        else:
            path = _inner_backend_path()
            self.inner = get_connection(path, fail_silently=fail_silently, **kwargs)
            self.without_server = path in LOG_ONLY_BACKENDS and not kwargs.get("host")

    def _sender(self, message: EmailMessage) -> None:
        """Through the system mailbox, a mail from the default sender goes out with the mailbox's address."""
        if self.mailbox is not None and message.from_email in ("", None, settings.DEFAULT_FROM_EMAIL):
            message.from_email = system_sender(self.mailbox)

    def open(self) -> Any:
        """Open the connection of the inner backend."""
        return self.inner.open()

    def close(self) -> None:
        """Close the connection of the inner backend."""
        self.inner.close()

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        """Send the messages one by one over one connection; note each as sent or failed.

        Returns:
            The number of messages sent, as the inner backend counts them – none
            without a mail server (EML-048).
        """
        if not email_messages:
            return 0
        for message in email_messages:
            self._sender(message)
            # EML-045: every system mail says that Rentalars sent it, for which company, from where.
            add_footer(message)
        try:
            opened = self.inner.open()
        except Exception as error:
            for message in email_messages:
                _note(message, LogResult.FAILED, str(error), self.mailbox)
            raise
        count = 0
        try:
            for message in email_messages:
                try:
                    sent = self.inner.send_messages([message]) or 0
                except Exception as error:
                    _note(message, LogResult.FAILED, str(error), self.mailbox)
                    raise
                if sent and self.without_server:
                    # EML-048: it went into the log of the server only; it does not count as sent.
                    _note(message, LogResult.NOT_SENT)
                    continue
                if sent:
                    _note(message, LogResult.SENT, mailbox=self.mailbox)
                elif message.recipients():
                    # With fail_silently the inner backend swallows the error and counts nothing.
                    _note(message, LogResult.FAILED, mailbox=self.mailbox)
                count += sent
        finally:
            if opened:
                self.inner.close()
        return count
