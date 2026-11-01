# SPDX-License-Identifier: GPL-3.0-or-later
"""Mailboxes in memory, and mails to put into them (EML tests).

The tests never talk to a real mail server. :class:`FakeMailbox` does what
``mail.imap.ImapMailbox`` does – list new headers, hand out a mail, move it
away – on a dictionary. Sending is caught by :func:`capture_smtp`.

:func:`configure_mailbox` sets up the mailbox of the correspondence that
sends as well (the one mailbox); :func:`add_mailbox` adds
further ones, and :func:`mailboxes` puts a fake mailbox in the place of each
real one, by address (EML-041).
"""

from __future__ import annotations

import contextlib
import datetime
import itertools
from collections.abc import Iterator
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from typing import Any
from unittest import mock

from rentalars.mail.imap import HeaderInfo, MailboxError, effective_action
from rentalars.mail.models import AfterAssignment, Mailbox, MailSettings

PASSWORD = "postfach-geheim"

#: Settings that hold for all mailboxes; :func:`configure_mailbox` puts them into ``MailSettings``.
RULES = frozenset({"sender_name", "signature_html", "interval_minutes", "max_message_mb", "retention_days"})

#: UIDs only ever grow in a mailbox; several fake mailboxes in one test continue the count.
_UIDS = itertools.count(1)


def configure_mailbox(**changes: Any) -> Mailbox:
    """Fill in and switch on the mailbox that fetches and sends the correspondence.

    ``changes`` may name fields of the mailbox and the rules of all mailboxes
    (``RULES``); ``is_enabled`` and ``delete_after_import`` keep
    their meaning.
    """
    rules = MailSettings.load()
    rules.sender_name = "Verleih Projekte"
    for name in RULES & set(changes):
        setattr(rules, name, changes.pop(name))
    rules.full_clean()
    rules.save()
    if "is_enabled" in changes:
        changes["is_active"] = changes.pop("is_enabled")
    if changes.pop("delete_after_import", False):
        changes["after_assignment"] = AfterAssignment.DELETE
    mailbox = Mailbox.objects.filter(address="projekte@verleih.example").first() or Mailbox(name="Projekte")
    mailbox.is_active = True
    mailbox.for_correspondence = True
    mailbox.is_outgoing = True
    mailbox.address = "projekte@verleih.example"
    mailbox.imap_host = "imap.verleih.example"
    mailbox.imap_user = "projekte@verleih.example"
    mailbox.smtp_host = "smtp.verleih.example"
    mailbox.set_imap_password(PASSWORD)
    for name, value in changes.items():
        setattr(mailbox, name, value)
    mailbox.full_clean()
    mailbox.save()
    return mailbox


def add_mailbox(name: str, address: str, **changes: Any) -> Mailbox:
    """A further mailbox of the correspondence, active and complete; ``changes`` set its fields (EML-041)."""
    mailbox = Mailbox(
        name=name,
        address=address,
        for_correspondence=True,
        imap_host=f"imap.{address.split('@')[-1]}",
        imap_user=address,
        smtp_host=f"smtp.{address.split('@')[-1]}",
    )
    mailbox.set_imap_password(PASSWORD)
    for field, value in changes.items():
        setattr(mailbox, field, value)
    mailbox.full_clean()
    mailbox.save()
    return mailbox


def make_mail(
    subject: str,
    *,
    sender: str = "Kunde <kunde@stadtwerke.example>",
    to: str = "projekte@verleih.example",
    text: str = "Hallo,\nanbei der Bühnenplan.\n",
    html: str | None = None,
    message_id: str | None = None,
    in_reply_to: str | None = None,
    attachments: list[tuple[str, str, bytes]] = (),  # type: ignore[assignment]
    date: datetime.datetime | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    """A mail as it arrives, e.g. ``make_mail("[RL#2027-0001] Bühnenplan")``.

    ``attachments`` are ``(file name, media type, content)``.
    """
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = format_datetime(date or datetime.datetime(2027, 3, 1, 7, 30, tzinfo=datetime.UTC))
    message["Message-ID"] = message_id or make_msgid(domain="stadtwerke.example")
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    for name, value in (headers or {}).items():
        message[name] = value
    message.set_content(text)
    if html is not None:
        message.add_alternative(html, subtype="html")
    for filename, content_type, data in attachments:
        maintype, _slash, subtype = content_type.partition("/")
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return message.as_bytes()


def header_part(raw: bytes) -> bytes:
    """The header of a mail, as ``BODY.PEEK[HEADER.FIELDS …]`` delivers it."""
    end = raw.find(b"\n\n")
    return raw if end < 0 else raw[: end + 2]


class FakeMailbox:
    """An inbox and a folder for assigned mails, in memory.

    ``inbox`` maps UIDs to mails; ``done`` collects what was filed away.
    ``fail`` makes every call raise :class:`MailboxError` with that text.
    """

    def __init__(self, *mails: bytes, validity: int = 7) -> None:
        self.validity = validity
        self.inbox: dict[int, bytes] = {}
        self.done: list[bytes] = []
        self.deleted: list[bytes] = []
        self.kept: list[int] = []
        self.read: list[int] = []
        self.fetched: list[int] = []
        self.fail = ""
        self.opened = 0
        #: EML-049: UIDs marked as read in the mailbox, and when a mail arrived (INTERNALDATE) if set.
        self.seen: set[int] = set()
        self.received: dict[int, datetime.datetime] = {}
        for mail in mails:
            self.add(mail)

    def add(self, raw: bytes, *, seen: bool = False, received: datetime.datetime | None = None) -> int:
        """Let a mail arrive – read already, at a given moment (EML-049); returns its UID."""
        uid = next(_UIDS)
        self.inbox[uid] = raw
        if seen:
            self.seen.add(uid)
        if received is not None:
            self.received[uid] = received
        return uid

    # The protocol of mail.imap.Mailbox ------------------------------------------------------

    def __call__(self, mail_settings: Any) -> FakeMailbox:
        """Act as the ``opener`` of ``fetch_mail``."""
        self.settings = mail_settings
        return self

    def __enter__(self) -> FakeMailbox:
        self._check()
        self.opened += 1
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def _check(self) -> None:
        if self.fail:
            raise MailboxError(self.fail)

    def select_inbox(self) -> int:
        self._check()
        return self.validity

    def headers_after(self, uid: int) -> list[HeaderInfo]:
        self._check()
        return [
            HeaderInfo(
                uid=key,
                size=len(raw),
                header=header_part(raw),
                seen=key in self.seen,
                received=self.received.get(key),
            )
            for key, raw in sorted(self.inbox.items())
            if key > uid
        ]

    def fetch(self, uid: int, *, limit: int | None = None) -> bytes:
        self._check()
        if uid not in self.inbox:
            raise MailboxError("The mail is no longer in the inbox.")
        self.fetched.append(uid)
        raw = self.inbox[uid]
        return raw[:limit] if limit else raw

    def file_away(self, uid: int, *, answer: bool = False) -> None:
        self._check()
        after = effective_action(self.settings, answer=answer)
        if after == AfterAssignment.KEEP:
            self.kept.append(uid)
            return
        if after == AfterAssignment.READ:
            # EML-006: only marked as read, it stays in the inbox.
            self.read.append(uid)
            return
        raw = self.inbox.pop(uid)
        (self.deleted if after == AfterAssignment.DELETE else self.done).append(raw)

    def find_uid(self, message_id: str) -> int | None:
        self._check()
        wanted = message_id.strip().strip("<>").lower()
        for uid, raw in self.inbox.items():
            if f"message-id: <{wanted}>".encode() in raw.lower():
                return uid
        return None

    def close(self) -> None:
        return None


@contextlib.contextmanager
def mailbox(*mails: bytes) -> Iterator[FakeMailbox]:
    """Put a :class:`FakeMailbox` in the place of the real one for the views and the timer."""
    box = FakeMailbox(*mails)
    with mock.patch("rentalars.mail.fetching.open_mailbox", box):
        yield box


@contextlib.contextmanager
def mailboxes(boxes: dict[str, FakeMailbox]) -> Iterator[dict[str, FakeMailbox]]:
    """Put a :class:`FakeMailbox` in the place of each real mailbox, found by its address (EML-041)."""

    def opener(mailbox: Any) -> FakeMailbox:
        return boxes[mailbox.address](mailbox)

    with mock.patch("rentalars.mail.fetching.open_mailbox", opener):
        yield boxes


@contextlib.contextmanager
def capture_smtp() -> Iterator[list[Any]]:
    """Catch what would go to the SMTP server; yields the list of sent messages."""
    sent: list[Any] = []

    def deliver(mailbox: Any, message: Any) -> None:
        message.mailbox = mailbox
        sent.append(message)

    with mock.patch("rentalars.mail.sending._send", deliver):
        yield sent
