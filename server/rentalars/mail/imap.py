# SPDX-License-Identifier: GPL-3.0-or-later
"""The connection to the mailbox over IMAP (EML-002, EML-005, EML-006).

A thin layer over ``imaplib`` from Python's standard library with exactly
the operations the fetch needs. The fetch only talks to :class:`Mailbox`;
the tests give it a mailbox in memory instead (``tests/unit/test_mail.py``).

What happens in the mailbox, and what does not:

* Looking at new mails reads only their headers with ``BODY.PEEK`` – the
  read state does not change (EML-005). With them come the flags (read or
  not) and the moment the mail arrived in the mailbox (``INTERNALDATE``):
  mails without tag are taken in only from a point in time, optionally only
  unread ones (EML-049).
* Only an assigned mail is read completely. Then the mailbox does what it
  is set to do with assigned mails (EML-006, EML-041): mark as read and move
  into the folder for assigned mails, only mark as read, delete – or
  leave it unchanged in the inbox.
* Moving uses ``MOVE`` where the server offers it, otherwise copy, mark as
  deleted and ``UID EXPUNGE`` – which removes only that one mail. A server
  that knows neither ``MOVE`` nor ``UIDPLUS`` is not supported: a plain
  ``EXPUNGE`` could remove mails somebody else marked as deleted.
"""

from __future__ import annotations

import contextlib
import datetime
import imaplib
import re
import ssl
from dataclasses import dataclass
from typing import Any, Protocol

from django.utils.translation import gettext as _

from rentalars.mail.models import AfterAssignment

#: Seconds to wait for the mail server before giving up.
TIMEOUT = 30
#: Headers fetched in one request.
BATCH = 200
# TO and CC only for the mail log (EML-039). ADM-013: REPLY-TO and the headers that mark a mail as
# sent automatically – an automation never answers those (``mail.parsing.automatic_reason``).
# EML-047: DELIVERED-TO and X-ORIGINAL-TO tell which address of the mailbox the mail went to.
HEADER_FIELDS = (
    "SUBJECT FROM TO CC DELIVERED-TO X-ORIGINAL-TO DATE MESSAGE-ID IN-REPLY-TO REFERENCES REPLY-TO RETURN-PATH "
    "CONTENT-TYPE AUTO-SUBMITTED "
    "PRECEDENCE LIST-ID LIST-UNSUBSCRIBE X-AUTOREPLY X-AUTORESPOND X-AUTO-RESPONSE-SUPPRESS"
)


class MailboxError(Exception):
    """The mailbox cannot be reached or refused something; the text says what (EML-032)."""


@dataclass
class HeaderInfo:
    """One new mail in the inbox, as far as the fetch looks at it."""

    uid: int
    size: int
    header: bytes
    deleted: bool = False
    #: EML-049: marked as read in the mailbox (flag ``Seen``).
    seen: bool = False
    #: EML-049: when the mail arrived in the mailbox (``INTERNALDATE``); ``None`` if the server did not say.
    received: datetime.datetime | None = None


class Mailbox(Protocol):
    """What the fetch needs from a mailbox."""

    def select_inbox(self) -> int:
        """Open the inbox; returns its UIDVALIDITY."""

    def headers_after(self, uid: int) -> list[HeaderInfo]:
        """The headers of all mails with a UID above ``uid``."""

    def fetch(self, uid: int, *, limit: int | None = None) -> bytes:
        """The whole mail – or its first ``limit`` bytes."""

    def file_away(self, uid: int, *, answer: bool = False) -> None:
        """Deal with an assigned mail as the mailbox is set: move, delete or leave (EML-006, EML-041).

        ``answer``: the mail answers a deployment request (PER-032); with "only mark as read" it is moved, too
        (PER-043).
        """

    def find_uid(self, message_id: str) -> int | None:
        """The UID of the mail with this Message-ID in the inbox, if it is still there."""

    def close(self) -> None:
        """Log out."""


#: The folder for assigned mails when none is named – the default of ``Mailbox.done_folder``.
DEFAULT_DONE_FOLDER = "Rentalars"


def effective_action(settings: Any, *, answer: bool = False) -> str:
    """What happens to an assigned mail in its mailbox (EML-006, PER-043).

    The setting of the mailbox – except for an answer to a deployment request
    under "only mark as read": that one is moved, unless there is no
    folder other than the inbox to move it to.
    """
    after = settings.after_assignment
    if (
        answer
        and after == AfterAssignment.READ
        and target_folder(settings).lower() != settings.inbox_folder.strip().lower()
    ):
        return AfterAssignment.MOVE
    return after


def target_folder(settings: Any) -> str:
    """The folder for assigned mails: the named one, else the default."""
    return (settings.done_folder or "").strip() or DEFAULT_DONE_FOLDER


def quote_folder(name: str) -> str:
    """A folder name as IMAP expects it: in quotes, with quotes and backslashes escaped."""
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


_UID = re.compile(rb"UID (\d+)")
_SIZE = re.compile(rb"RFC822\.SIZE (\d+)")
_FLAGS = re.compile(rb"FLAGS \(([^)]*)\)")
_INTERNALDATE = re.compile(rb'INTERNALDATE "([^"]+)"')
_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1
    )
}


def parse_internaldate(value: bytes | str) -> datetime.datetime | None:
    """``17-Jul-1996 02:44:25 -0700`` (RFC 3501 ``date-time``) as an aware datetime; ``None`` if unreadable (EML-049).

    Parsed by hand: ``strptime`` reads month names in the language of the process.
    """
    text = value.decode("ascii", "replace") if isinstance(value, bytes) else value
    match = re.fullmatch(r"\s*(\d{1,2})-([A-Za-z]{3})-(\d{4}) (\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})\s*", text)
    if match is None:
        return None
    day, month_name, year, hour, minute, second, sign, off_hours, off_minutes = match.groups()
    month = _MONTHS.get(month_name.lower())
    if month is None:
        return None
    offset = datetime.timedelta(hours=int(off_hours), minutes=int(off_minutes))
    try:
        return datetime.datetime(
            int(year),
            month,
            int(day),
            int(hour),
            int(minute),
            int(second),
            tzinfo=datetime.timezone(-offset if sign == "-" else offset),
        )
    except ValueError:
        return None


class ImapMailbox:
    """The real mailbox, reached with ``imaplib``."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.imap: imaplib.IMAP4 | None = None
        self.capabilities: set[str] = set()

    # --- Connecting --------------------------------------------------------------------------

    def __enter__(self) -> ImapMailbox:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def open(self) -> None:
        """Connect – always encrypted (EML-002) – and log in."""
        settings = self.settings
        context = ssl.create_default_context()
        # NFA-071: the server a mailbox names is connected to only at a checked address.
        from rentalars.core.network import BlockedAddressError, GuardedIMAP4, GuardedIMAP4SSL

        try:
            if settings.imap_security == "ssl":
                self.imap = GuardedIMAP4SSL(
                    settings.imap_host, settings.imap_port, ssl_context=context, timeout=TIMEOUT
                )
            else:
                self.imap = GuardedIMAP4(settings.imap_host, settings.imap_port, timeout=TIMEOUT)
                self.imap.starttls(ssl_context=context)
            self.imap.login(settings.imap_user, settings.imap_password)
            self.capabilities = {str(item).upper() for item in self.imap.capabilities}
        except imaplib.IMAP4.error as error:
            raise MailboxError(_("The mail server refused the login: %(error)s") % {"error": _text(error)}) from error
        except ssl.SSLError as error:
            raise MailboxError(
                _("No encrypted connection to the mail server: %(error)s") % {"error": _text(error)}
            ) from error
        except BlockedAddressError as error:
            raise MailboxError(str(error)) from error
        except (TimeoutError, OSError) as error:
            raise MailboxError(
                _("The mail server %(host)s:%(port)s cannot be reached: %(error)s")
                % {"host": settings.imap_host, "port": settings.imap_port, "error": _text(error)}
            ) from error

    def close(self) -> None:
        """Log out; errors on the way out do not matter any more."""
        if self.imap is not None:
            with contextlib.suppress(imaplib.IMAP4.error, OSError):
                self.imap.logout()
            self.imap = None

    def _call(self, what: str, method: Any, *args: Any) -> list[Any]:
        try:
            status, data = method(*args)
        except imaplib.IMAP4.error as error:
            raise MailboxError(_("%(what)s failed: %(error)s") % {"what": what, "error": _text(error)}) from error
        except (TimeoutError, OSError) as error:
            raise MailboxError(
                _("The connection to the mail server broke off: %(error)s") % {"error": _text(error)}
            ) from error
        if status != "OK":
            raise MailboxError(_("%(what)s failed: %(error)s") % {"what": what, "error": _text(data)})
        return list(data or [])

    # --- The operations of the fetch ------------------------------------------------------------

    def select_inbox(self) -> int:
        """Open the inbox for reading and changing; returns its UIDVALIDITY."""
        assert self.imap is not None
        self._call(_("Opening the inbox"), self.imap.select, quote_folder(self.settings.inbox_folder))
        response = self.imap.response("UIDVALIDITY")[1]
        try:
            return int(response[0]) if response and response[0] else 0
        except (TypeError, ValueError):
            return 0

    def headers_after(self, uid: int) -> list[HeaderInfo]:
        """The headers of the mails with a higher UID; nothing is changed (EML-005)."""
        assert self.imap is not None
        data = self._call(_("Searching the inbox"), self.imap.uid, "SEARCH", None, f"UID {uid + 1}:*")
        uids = sorted(int(value) for value in (data[0] or b"").split() if int(value) > uid)
        result: list[HeaderInfo] = []
        for start in range(0, len(uids), BATCH):
            chunk = ",".join(str(value) for value in uids[start : start + BATCH])
            # EML-049: FLAGS (read or not) and INTERNALDATE (arrival) decide about mails without tag.
            items = f"(UID RFC822.SIZE FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])"
            for entry in self._call(_("Reading headers"), self.imap.uid, "FETCH", chunk, items):
                if not isinstance(entry, tuple) or len(entry) < 2:
                    continue
                meta, header = entry[0], entry[1]
                found_uid = _UID.search(meta)
                if found_uid is None:
                    continue
                size = _SIZE.search(meta)
                flags = _FLAGS.search(meta)
                arrived = _INTERNALDATE.search(meta)
                result.append(
                    HeaderInfo(
                        uid=int(found_uid.group(1)),
                        size=int(size.group(1)) if size else 0,
                        header=header,
                        deleted=bool(flags and b"\\Deleted" in flags.group(1)),
                        seen=bool(flags and b"\\Seen" in flags.group(1)),
                        received=parse_internaldate(arrived.group(1)) if arrived else None,
                    )
                )
        return sorted(result, key=lambda info: info.uid)

    def fetch(self, uid: int, *, limit: int | None = None) -> bytes:
        """The whole mail, without marking it as read; or only its beginning."""
        assert self.imap is not None
        section = f"BODY.PEEK[]<0.{limit}>" if limit else "BODY.PEEK[]"
        for entry in self._call(_("Reading a mail"), self.imap.uid, "FETCH", str(uid), f"({section})"):
            if isinstance(entry, tuple) and len(entry) >= 2:
                return bytes(entry[1])
        raise MailboxError(_("The mail is no longer in the inbox."))

    def _ensure_folder(self, folder: str) -> None:
        assert self.imap is not None
        status, _data = self.imap.create(quote_folder(folder))
        # "already exists" is the usual answer from the second time on; nothing to do then.
        if status != "OK":
            self.imap.subscribe(quote_folder(folder))

    def file_away(self, uid: int, *, answer: bool = False) -> None:
        """Deal with an assigned mail as the mailbox is set (EML-006, EML-041).

        "Move": mark as read and move into the folder for assigned mails.
        "Only mark as read" (EML-006): mark as read, leave in the inbox –
        except an answer to a deployment request (``answer``, PER-043):
        that one is moved into the folder, too, so that the inbox keeps the
        mails somebody has to read. "Delete": mark as read and remove.
        "Leave": change nothing, not even the read state; the fetch does not
        look at the mail again.
        """
        assert self.imap is not None
        after = effective_action(self.settings, answer=answer)
        if after == AfterAssignment.KEEP:
            return
        number = str(uid)
        self._call(_("Marking as read"), self.imap.uid, "STORE", number, "+FLAGS", "(\\Seen)")
        if after == AfterAssignment.READ:
            return  # EML-006: only marked as read; the fetch does not look at it again.
        if after == AfterAssignment.DELETE:
            self._remove(number)
            return
        folder = target_folder(self.settings)
        self._ensure_folder(folder)
        if "MOVE" in self.capabilities:
            self._call(_("Moving the mail"), self.imap.uid, "MOVE", number, quote_folder(folder))
            return
        self._call(_("Copying the mail"), self.imap.uid, "COPY", number, quote_folder(folder))
        self._remove(number)

    def _remove(self, number: str) -> None:
        assert self.imap is not None
        if "UIDPLUS" not in self.capabilities:
            raise MailboxError(
                _("The mail server knows neither MOVE nor UIDPLUS; Rentalars cannot remove a single mail safely.")
            )
        self._call(_("Deleting the mail"), self.imap.uid, "STORE", number, "+FLAGS", "(\\Deleted)")
        self._call(_("Deleting the mail"), self.imap.uid, "EXPUNGE", number)

    def find_uid(self, message_id: str) -> int | None:
        """Search the inbox for a Message-ID (for assigning by hand, EML-014)."""
        assert self.imap is not None
        cleaned = message_id.strip().replace('"', "")
        data = self._call(
            _("Searching the inbox"), self.imap.uid, "SEARCH", None, "HEADER", "Message-ID", f'"{cleaned}"'
        )
        found = (data[0] or b"").split() if data else []
        return int(found[-1]) if found else None


def _text(value: object) -> str:
    """An error of ``imaplib`` as readable text."""
    if isinstance(value, list):
        value = b" ".join(item if isinstance(item, bytes) else str(item).encode() for item in value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return str(value).strip()[:300]


def open_mailbox(settings: Any) -> ImapMailbox:
    """Return the configured mailbox, to be used in a ``with`` block that logs in and out."""
    return ImapMailbox(settings)
