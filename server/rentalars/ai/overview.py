# SPDX-License-Identifier: GPL-3.0-or-later
"""The short overview of a correspondence, without AI (EML-040, EML-044).

Always available, also before any AI is installed: who took part, how many
mails, the first and the last, the dates and amounts the mails mention,
open questions of the latest mails (sentences ending in "?"), the
attachments, and who wrote last. Everything is taken from the mails as they
are – nothing is made up, nothing is sent anywhere.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from email.utils import getaddresses
from typing import Any

from django.utils import timezone

from rentalars.ai.correspondence import mails_of, new_text_of, writer_of
from rentalars.mail.models import Direction, MailAttachment

#: How many of the newest mails are read for dates and amounts; how many for questions.
SCANNED_MAILS = 200
QUESTION_MAILS = 3
MAX_ITEMS = 12

_MONTHS = {
    "januar": 1, "jan": 1, "january": 1,
    "februar": 2, "feb": 2, "february": 2,
    "märz": 3, "maerz": 3, "mrz": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12, "december": 12, "dec": 12,
}  # fmt: skip
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))

_NUMERIC_DATE = re.compile(r"(?<![\d.,/])([0-3]?\d)\.\s?([01]?\d)\.(?:\s?(\d{4})|\s?(\d{2})(?![\d.]))?(?!\d)")
_SLASH_DATE = re.compile(r"(?<![\d/.])([0-3]?\d)/([01]?\d)/(\d{4})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_NAMED_DATE = re.compile(rf"(?<!\d)([0-3]?\d)\.?\s+({_MONTH_NAMES})\b\.?(?:\s+(\d{{4}}))?", re.IGNORECASE)
_NUMBER = (
    r"\d{1,3}(?:[.\u00a0\u202f ]\d{3})+(?:,\d{1,2}|,-)?|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"
    r"|\d+\.\d{2}(?!\d)|\d+(?:,\d{1,2}|,-)?"
)
_AMOUNT = re.compile(rf"(?:(?:€|EUR)\s?(?:{_NUMBER}))|(?:(?<![\d.,])(?:{_NUMBER})\s?(?:€|EUR\b|Euro\b))", re.IGNORECASE)
#: A sentence ending in "?"; a dot inside it (a date, an abbreviation) does not end it.
_QUESTION = re.compile(r"(?:[^.!?\n]|\.(?!\s))+\?")


@dataclass
class Mention:
    """A date or an amount, with the mail it is from."""

    text: str
    mail: Any
    date: datetime.date | None = None


@dataclass
class Participant:
    """Someone who wrote in the correspondence, or received it."""

    name: str
    written: int = 0


@dataclass
class Overview:
    """The short overview (EML-044)."""

    mail_count: int = 0
    received: int = 0
    sent: int = 0
    #: EML-051: notes written into the correspondence.
    notes: int = 0
    first: Any = None
    last: Any = None
    writers: list[Participant] = field(default_factory=list)
    recipients: list[str] = field(default_factory=list)
    dates: list[Mention] = field(default_factory=list)
    amounts: list[Mention] = field(default_factory=list)
    questions: list[Mention] = field(default_factory=list)
    attachments: list[MailAttachment] = field(default_factory=list)
    more_attachments: int = 0
    last_writer: str = ""
    #: Whether the dates and amounts come from the newest :data:`SCANNED_MAILS` mails only.
    scanned_part: bool = False

    @property
    def last_is_incoming(self) -> bool:
        """Whether the last mail came in – an answer may be due."""
        return self.last is not None and self.last.direction == Direction.INCOMING


def _valid(year: int, month: int, day: int) -> datetime.date | None:
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _with_year(day: int, month: int, year: int | None, sent: datetime.date) -> datetime.date | None:
    """A date written without the year: the next such day from two months before the mail on."""
    if year is not None:
        if year < 100:
            year += 2000
        return _valid(year, month, day)
    found = _valid(sent.year, month, day)
    if found is not None and found < sent - datetime.timedelta(days=60):
        found = _valid(sent.year + 1, month, day)
    return found


def dates_in(text: str, sent: datetime.date) -> list[tuple[str, datetime.date]]:
    """The dates a text mentions, as written and as dates (German, British and ISO forms)."""
    found: list[tuple[str, datetime.date]] = []
    for match in _NUMERIC_DATE.finditer(text):
        day, month = int(match.group(1)), int(match.group(2))
        year = match.group(3) or match.group(4)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            continue
        value = _with_year(day, month, int(year) if year else None, sent)
        if value:
            found.append((match.group(0).strip(), value))
    for match in _SLASH_DATE.finditer(text):
        value = _valid(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if value:
            found.append((match.group(0), value))
    for match in _ISO_DATE.finditer(text):
        value = _valid(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if value:
            found.append((match.group(0), value))
    for match in _NAMED_DATE.finditer(text):
        month = _MONTHS.get(match.group(2).lower())
        if month:
            value = _with_year(int(match.group(1)), month, int(match.group(3)) if match.group(3) else None, sent)
            if value:
                found.append((" ".join(match.group(0).split()), value))
    return found


def amounts_in(text: str) -> list[str]:
    """The amounts of money a text mentions, as written (euro)."""
    return [" ".join(match.group(0).replace(" ", " ").replace(" ", " ").split()) for match in _AMOUNT.finditer(text)]


def questions_in(text: str) -> list[str]:
    """The sentences of a text that end in a question mark."""
    found = []
    for line in text.splitlines():
        if "?" not in line:
            continue
        for match in _QUESTION.finditer(line[:2000]):
            sentence = " ".join(match.group(0).split()).lstrip("-–•*> ")
            if 8 <= len(sentence) <= 300 and not sentence.lower().startswith(("http", "www.")):
                found.append(sentence)
    return found


def overview_of(project_ids: list[int]) -> Overview:
    """The short overview of the mails of these projects (EML-044)."""
    mails = mails_of(project_ids)
    result = Overview()
    ordered = list(mails.select_related("sent_by").order_by("-date", "-id")[:SCANNED_MAILS])
    if not ordered:
        return result
    result.mail_count = mails.count()
    result.received = mails.filter(direction=Direction.INCOMING).count()
    # EML-051: notes are neither received nor sent.
    result.notes = mails.filter(direction=Direction.NOTE).count()
    result.sent = result.mail_count - result.received - result.notes
    result.last = next((mail for mail in ordered if not mail.is_note), ordered[0])
    result.first = mails.order_by("date", "id").first()
    result.last_writer = writer_of(result.last)
    result.scanned_part = result.mail_count > len(ordered)

    writers: dict[str, Participant] = {}
    recipients: dict[str, str] = {}
    seen_dates: set[datetime.date] = set()
    seen_amounts: set[str] = set()
    for index, mail in enumerate(ordered):
        writer = writer_of(mail)
        writers.setdefault(writer.lower(), Participant(writer)).written += 1
        for name, address in getaddresses([mail.to_addresses, mail.cc_addresses]):
            if address:
                recipients.setdefault(address.lower(), f"{name} <{address}>" if name else address)
        text = new_text_of(mail, limit=20_000)
        sent = timezone.localtime(mail.date).date() if timezone.is_aware(mail.date) else mail.date.date()
        for written, value in dates_in(text, sent):
            if value not in seen_dates:
                seen_dates.add(value)
                result.dates.append(Mention(written, mail, value))
        for amount in amounts_in(text):
            key = amount.lower()
            if key not in seen_amounts:
                seen_amounts.add(key)
                result.amounts.append(Mention(amount, mail))
        if index < QUESTION_MAILS:
            result.questions += [Mention(question, mail) for question in questions_in(text)]
    result.writers = sorted(writers.values(), key=lambda person: (-person.written, person.name.lower()))[:MAX_ITEMS]
    writer_texts = " ".join(person.name.lower() for person in result.writers)
    result.recipients = [label for address, label in recipients.items() if address not in writer_texts][:MAX_ITEMS]
    result.dates = sorted(result.dates, key=lambda mention: mention.date or datetime.date.min)[:MAX_ITEMS]
    result.amounts = result.amounts[:MAX_ITEMS]
    result.questions = result.questions[:8]
    attachments = MailAttachment.objects.filter(mail__in=mails, is_inline=False).select_related("mail")
    result.attachments = list(attachments.order_by("-mail__date", "-id")[:MAX_ITEMS])
    result.more_attachments = max(0, attachments.count() - len(result.attachments))
    return result
