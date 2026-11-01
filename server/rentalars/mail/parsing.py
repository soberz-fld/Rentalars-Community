# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading a raw e-mail into what Rentalars stores (EML-019, EML-020, EML-030).

Uses the ``email`` package of Python's standard library with its modern
policy, which decodes encoded subjects, names and texts. Mails in the wild
are often not quite correct; every step here falls back to something
reasonable instead of failing – a mail that cannot be read perfectly is
still better taken over than lost.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from dataclasses import dataclass, field
from email import errors, policy
from email.message import EmailMessage, Message
from email.parser import BytesHeaderParser, BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from django.utils import timezone

from rentalars.mail.models import MailKind, message_key

_MESSAGE_IDS = re.compile(r"<[^<>\s]+>")


@dataclass
class Attachment:
    """An attachment as found in the mail."""

    filename: str
    content_type: str
    data: bytes
    content_id: str = ""
    is_inline: bool = False

    @property
    def size(self) -> int:
        """The size in bytes."""
        return len(self.data)


@dataclass
class Headers:
    """What the fetch looks at before deciding to take a mail over (EML-005).

    ``to`` holds the recipients (To and CC) for the mail log (EML-039).
    ``delivered`` the addresses the mail server delivered it to (EML-047).
    ADM-013: ``reply_to`` is where an automatic answer goes, ``automatic``
    why the mail itself counts as sent automatically (:func:`automatic_reason`).
    """

    subject: str = ""
    sender: str = ""
    date: datetime.datetime | None = None
    message_id: str = ""
    in_reply_to: str = ""
    references: str = ""
    to: str = ""
    reply_to: str = ""
    automatic: str = ""
    #: EML-047: the addresses of ``Delivered-To`` and ``X-Original-To``, in this order – with ``to``
    #: they tell which address of a mailbox the mail went to (``mail.aliases.alias_for``).
    delivered: str = ""

    @property
    def key(self) -> str:
        """The key by which the mail is recognised again (EML-007)."""
        return message_key(self.message_id or self.fallback_id)

    @property
    def fallback_id(self) -> str:
        """A stand-in for a missing Message-ID: built from what else identifies the mail."""
        date = self.date.isoformat() if self.date else ""
        return f"<no-message-id.{message_key(self.sender + '|' + self.subject + '|' + date)[:32]}@rentalars>"

    @property
    def referenced_keys(self) -> list[str]:
        """The keys of all mails this one refers to (EML-012)."""
        ids = _MESSAGE_IDS.findall(f"{self.in_reply_to} {self.references}")
        return [message_key(message_id) for message_id in dict.fromkeys(ids)]


@dataclass
class ParsedMail(Headers):
    """A whole mail: headers, texts and attachments."""

    sender_name: str = ""
    sender_address: str = ""
    to: str = ""
    cc: str = ""
    text: str = ""
    html: str = ""
    kind: str = MailKind.NORMAL
    attachments: list[Attachment] = field(default_factory=list)
    #: PER-032: what the receiving mail server wrote in its ``Authentication-Results`` headers (SPF, DKIM,
    #: DMARC); empty if it wrote none.
    authentication: str = ""
    #: How many ``From`` headers the mail has. More than one is a trick (a receiver may check the other one).
    from_count: int = 1
    #: S2: the sender as the structured header gives it – exactly one address with a domain and no defect in
    #: the header; empty otherwise. ``sender_address`` stays what ``parseaddr`` makes of the line (it is for sorting
    #: mails, not for trusting them): from ``From: "anna@mail.example"`` it makes ``anna@mail.example``.
    sender_checked: str = ""
    #: Each ``Authentication-Results`` header of its own (``authentication`` has them in one line).
    authentication_headers: list[str] = field(default_factory=list)


def _text(value: object) -> str:
    """A header value as one line of text."""
    return " ".join(str(value or "").split())


#: Characters that make a display name need quotes in an address list.
_SPECIALS = re.compile(r'[,;:<>()\[\]@"\\]')


def format_address(name: str, address: str) -> str:
    """``"Müller, Hans" <h@x.example>`` – readable, and safe to split at commas again (EML-037).

    Unlike ``email.utils.formataddr`` the name is not encoded: the result is
    shown to people and stored; the ``email`` package encodes it when the
    mail is sent.
    """
    name = " ".join((name or "").split())
    if not name:
        return address
    if _SPECIALS.search(name):
        name = '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{name} <{address}>"


def _date(value: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed


def parse_headers(raw: bytes) -> Headers:
    """Read only the headers of a mail – enough to decide about it (EML-005)."""
    message = BytesHeaderParser(policy=policy.default).parsebytes(raw)
    return _headers_of(message)


def _headers_of(message: Message) -> Headers:
    recipients = [part for part in (_addresses(message, "To"), _addresses(message, "Cc")) if part]
    return Headers(
        subject=_text(message.get("Subject", "")),
        sender=_text(message.get("From", "")),
        date=_date(str(message.get("Date", "") or "")),
        message_id=_text(message.get("Message-ID", "")),
        in_reply_to=_text(message.get("In-Reply-To", "")),
        references=_text(message.get("References", "")),
        to=", ".join(recipients),
        reply_to=_addresses(message, "Reply-To"),
        automatic=automatic_reason(message),
        delivered=", ".join(
            part for part in (_addresses(message, "Delivered-To"), _addresses(message, "X-Original-To")) if part
        ),
    )


#: ADM-013: values of ``Precedence`` that mark mass and automatic mail.
_AUTOMATIC_PRECEDENCE = frozenset({"bulk", "junk", "list", "auto_reply"})


def automatic_reason(message: Message) -> str:
    """The header that marks a mail as sent automatically, e.g. ``Precedence: bulk``; empty for a normal mail.

    ADM-013: an automation never answers such a mail – an out-of-office
    reply, a delivery failure, a mailing list, a newsletter, another
    system's confirmation – so that automatic answers cannot set each
    other off (RFC 3834). Who sent it (mailer-daemon, no-reply, an own
    address) is checked by the automation itself.
    """
    try:
        auto_submitted = _text(message.get("Auto-Submitted", ""))
        if auto_submitted and auto_submitted.lower() != "no":
            return f"Auto-Submitted: {auto_submitted}"
        precedence = _text(message.get("Precedence", ""))
        if precedence.lower() in _AUTOMATIC_PRECEDENCE:
            return f"Precedence: {precedence}"
        for name in ("List-Id", "List-Unsubscribe", "X-Autoreply", "X-Autorespond"):
            if message.get(name):
                return f"{name}: {_text(message.get(name))[:80]}"
        suppress = _text(message.get("X-Auto-Response-Suppress", ""))
        if suppress and {part.strip().lower() for part in suppress.split(",")} & {"all", "oof", "autoreply"}:
            return f"X-Auto-Response-Suppress: {suppress}"
        if message.get("Return-Path") is not None and _text(message.get("Return-Path")) in ("<>", ""):
            return "Return-Path: <>"
        if message.get_content_type() == "multipart/report":
            return "Content-Type: multipart/report"
    except (TypeError, ValueError, IndexError):
        # A header so broken that it cannot be read: rather no answer than a wrong one.
        return "?"
    return ""


def _addresses(message: Message, name: str) -> str:
    try:
        values = [str(value) for value in message.get_all(name, [])]
    except (TypeError, ValueError, IndexError):
        # A header so broken that the email package cannot even show it.
        return ""
    return ", ".join(format_address(display, address) for display, address in getaddresses(values) if address)


def _content(part: Message) -> str:
    """The decoded text of a part, also with an unknown or wrong character set."""
    try:
        content = part.get_content()  # type: ignore[attr-defined]
        if isinstance(content, str):
            return content
    except (LookupError, UnicodeError, KeyError, AssertionError):
        pass
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")  # type: ignore[union-attr]
    except LookupError:
        return payload.decode("utf-8", errors="replace")  # type: ignore[union-attr]


def detect_kind(message: Message) -> str:
    """An automatic reply or a delivery failure is marked as such (EML-030)."""
    content_type = message.get_content_type()
    report_type = (message.get_param("report-type") or "").lower() if content_type == "multipart/report" else ""
    sender = parseaddr(str(message.get("From", "")))[1].lower()
    if report_type == "delivery-status" or sender.startswith(("mailer-daemon@", "postmaster@")):
        return MailKind.BOUNCE
    auto_submitted = str(message.get("Auto-Submitted", "")).strip().lower()
    precedence = str(message.get("Precedence", "")).strip().lower()
    if (
        (auto_submitted and auto_submitted != "no")
        or message.get("X-Autoreply")
        or message.get("X-Autorespond")
        or message.get("X-Auto-Response-Suppress", "").lower() in {"all", "oof"}
        or precedence in {"auto_reply", "bulk", "junk"}
    ):
        return MailKind.AUTO_REPLY
    return MailKind.NORMAL


def _unescaped(text: str) -> str:
    """Characters that the parser kept as surrogate escapes (raw UTF-8 in a header, RFC 6532) as what they are."""
    try:
        return text.encode("ascii", "surrogateescape").decode("utf-8")
    except UnicodeError:
        return text


def _checked_sender(message: EmailMessage) -> str:
    """The address of the ``From`` header, read as the structure it is (S2); ``""`` if it is not clean.

    ``parseaddr`` on the line makes an address of a quoted text (``From: "anna@mail.example"``) or of an encoded word
    without an address; the structured reading says what it is: no domain, a defect of the header. Clean means: one
    address, a local part and a domain, no defect (raw UTF-8 in the header is allowed), and a domain with other than
    ASCII characters is one that does not change under NFKC (no full-width letters) and has no invisible format
    characters (soft hyphen, zero-width space).
    """
    header = message.get("From")
    addresses = getattr(header, "addresses", None)
    if not addresses or len(addresses) != 1:
        return ""
    # Raw UTF-8 and obsolete but unambiguous syntax (dots in a display name: ``J. Smith <j@x.example>``) are fine; any
    # other defect means that the header is not what it seems.
    harmless = (errors.UndecodableBytesDefect, errors.ObsoleteHeaderDefect)
    if any(not isinstance(defect, harmless) for defect in getattr(header, "defects", ())):
        return ""
    local, domain = _unescaped(addresses[0].username), _unescaped(addresses[0].domain)
    if not local or not domain or "@" in domain:
        return ""
    if not domain.isascii() and (
        unicodedata.normalize("NFKC", domain) != domain or any(unicodedata.category(char) == "Cf" for char in domain)
    ):
        return ""
    return f"{local}@{domain}"


def parse_mail(raw: bytes) -> ParsedMail:
    """Read a whole mail (EML-019, EML-020)."""
    message: EmailMessage = BytesParser(policy=policy.default).parsebytes(raw)  # type: ignore[assignment]
    headers = _headers_of(message)
    name, address = parseaddr(str(message.get("From", "")))
    parsed = ParsedMail(**headers.__dict__)
    parsed.sender_name = _text(name)[:200]
    parsed.sender_address = address[:254]
    parsed.to = _addresses(message, "To")
    parsed.cc = _addresses(message, "Cc")
    parsed.kind = detect_kind(message)
    parsed.authentication = " ".join(_text(value) for value in message.get_all("Authentication-Results", []))
    parsed.authentication_headers = [_text(value) for value in message.get_all("Authentication-Results", [])]
    parsed.from_count = len(message.get_all("From", []))
    parsed.sender_checked = _checked_sender(message)

    plain = html = None
    try:
        plain = message.get_body(preferencelist=("plain",))
        html = message.get_body(preferencelist=("html",))
    except (KeyError, AttributeError):
        pass
    if plain is not None:
        parsed.text = _content(plain)
    if html is not None:
        parsed.html = _content(html)
    if plain is None and html is None and not message.is_multipart():
        parsed.text = _content(message)

    for part in message.walk():
        if part.is_multipart() or part is plain or part is html:
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        content_id = _text(part.get("Content-ID", "")).strip("<>")
        is_image = part.get_content_maintype() == "image"
        if not (filename or disposition == "attachment" or (content_id and is_image)):
            continue
        if part.get_content_type() == "message/rfc822" and not filename:
            filename = "weitergeleitete-mail.eml"
        data = part.get_payload(decode=True)
        if data is None:
            # A message/rfc822 part: its payload is a message, not bytes.
            inner = part.get_payload()
            data = (
                inner[0].as_bytes()
                if isinstance(inner, list) and inner and hasattr(inner[0], "as_bytes")
                else str(inner).encode("utf-8", "replace")
            )
        parsed.attachments.append(
            Attachment(
                filename=_text(filename) or f"anhang-{len(parsed.attachments) + 1}",
                content_type=part.get_content_type(),
                data=data,
                content_id=content_id,
                is_inline=disposition == "inline" or (bool(content_id) and disposition != "attachment"),
            )
        )
    return parsed
