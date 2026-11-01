# SPDX-License-Identifier: GPL-3.0-or-later
"""Answering a deployment request by reply mail (PER-032).

Why
---
A deployment request (PER-016) reaches the person as a notification; its mail
carries a link into Rentalars. The link needs the server to be reachable from
the internet. An answer by mail does not: the request mail carries two buttons,
"Accept" and "Decline" – ``mailto:`` links that open a prepared mail to a
mailbox Rentalars fetches anyway. The answer travels through the mail servers;
Rentalars only fetches it, as it fetches the correspondence.

``MailSettings.crew_answers`` chooses: the link, the reply
mail, or both (the default). Answers by mail need a mailbox that is fetched
and can take them (:func:`answer_mailbox`): the mailbox that sends the request
– the system mailbox – if it is one of the correspondence, else the mailbox
that sends the correspondence. Without one the request carries only the link.

The tag
-------
The subject of the prepared mail ends with ``[RA-E-<token>-JA]`` (accept) or
``[RA-E-<token>-NEIN]`` (decline). The token is random (120 bits) and stored
with the request (:class:`~rentalars.mail.models.CrewRequestMail`); it stands
for one request to one person.

The sender
-------------------
The token alone would let anybody who holds the request mail answer – a
request the person forwards could be answered by its new holder in the name
of the person. So the request stores the address it was sent to
(``CrewRequestMail.sent_to``) and an answer counts only if the mail comes
from exactly that address (:func:`sender_reason`). A mail from another
address changes nothing; the person gets a mail at the address asked, saying
so. A sender address can be forged, though: if the receiving mail server
writes an ``Authentication-Results`` header and it says that DMARC failed,
the mail is refused as well. Without such a header, or with another result,
the address cannot be checked further – that depends on the mail servers
of the person and of the company (see the operations manual).

Free replies ("Ja", "Nein") are not read: a reply quotes the request with both
words, signatures and wording vary, and a wrong answer recorded is worse than
none. They stay normal mails – the request mail names the mailbox for answers
as "Reply-To", so that they reach a mailbox somebody reads.

The fetch
---------
``mail.fetching`` hands every mail to :func:`take_answer` first, in every
mailbox, whatever the mailbox does with mails without tag. A tag with a known
token is an answer:

* the request still waits: the answer is recorded by
  ``projects.crew.answer_deployment`` – the service of the browser, with its
  notifications – with the note written behind "Note:", acting as the person;
  the history notes that it came by mail; the person gets a confirmation;
* answered already, the deployment over, the request withdrawn or replaced by
  a newer one, the project cancelled or closed, the mail from another address
  than the one asked or with a forged sender: nothing changes, and the person
  gets a mail saying so (at their own address, never to the sender);
* either way the mail is noted in the mail log as "answer to a deployment
  request" and then dealt with as the mailbox deals with assigned mails (move,
  delete or leave) – except that "only mark as read" moves an answer into the folder, too (PER-043).

An unknown token, and an automatic reply that carries a tag, are normal mails.
The mails Rentalars sends here are marked ``Auto-Submitted`` and the
confirmations carry no tag, so that no out-of-office reply starts a loop.
"""

from __future__ import annotations

import base64
import logging
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import formats, timezone, translation
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rentalars.core.audit import acting_as, record_event
from rentalars.core.i18n import for_user, local_pattern
from rentalars.mail import log
from rentalars.mail.display import html_to_text, split_quoted
from rentalars.mail.mailboxes import outgoing_mailbox, system_mailbox
from rentalars.mail.models import (
    CREW_ANSWER_DETAILS,
    CrewAnswerMode,
    CrewRequestMail,
    Direction,
    LogResult,
    Mailbox,
    MailKind,
    MailLogEntry,
    MailSettings,
)
from rentalars.mail.parsing import Headers, ParsedMail, parse_mail

if TYPE_CHECKING:
    from rentalars.mail.imap import Mailbox as MailboxConnection
    from rentalars.projects.models import CrewLine

logger = logging.getLogger(__name__)

#: The tag in the subject of an answer: ``[RA-E-<token>-JA]`` or ``[RA-E-<token>-NEIN]``.
TAG_PREFIX = "RA-E"
ACCEPT_CODE = "JA"
DECLINE_CODE = "NEIN"
#: 15 random bytes – 120 bits – are 24 characters of base32 (a–z, 2–7).
TOKEN_BYTES = 15
_TAG = re.compile(
    rf"\[\s*{TAG_PREFIX}-([a-z2-7]{{24}})-({ACCEPT_CODE}|{DECLINE_CODE})\s*\]",
    re.IGNORECASE,
)

#: How much of an answer is read: its text; attachments do not matter here.
TEXT_LIMIT = 512 * 1024

#: The line of dashes that ends the note in the prepared mail.
_NOTE_END = re.compile(r"^\s*-{3,}\s*$")
#: The longest note, as the answer of the browser keeps it (``CrewLine.answer_note``).
NOTE_MAX_LENGTH = 250

#: Why an answer was not taken over (``mail.models.CREW_ANSWER_REASONS``).
ANSWERED = "answered"
EXPIRED = "expired"
WITHDRAWN = "withdrawn"
REPLACED = "replaced"
CANCELLED = "cancelled"
#: PER-032: not from the address the request went to / the mail server says the sender is forged.
SENDER = "sender"
FORGED = "forged"
#: S2: the mail server named in the settings did not confirm the sender.
UNCONFIRMED = "unconfirmed"


# --- The tag ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AnswerTag:
    """What the tag in the subject of an answer says."""

    token: str
    accept: bool


def new_token() -> str:
    """A random token that nobody can guess: 24 characters, a–z and 2–7."""
    return base64.b32encode(secrets.token_bytes(TOKEN_BYTES)).decode("ascii").lower()


def tag_for(token: str, *, accept: bool) -> str:
    """The tag of an answer: ``[RA-E-<token>-JA]`` or ``[RA-E-<token>-NEIN]``."""
    return f"[{TAG_PREFIX}-{token}-{ACCEPT_CODE if accept else DECLINE_CODE}]"


def find_tag(subject: str) -> AnswerTag | None:
    """The tag of an answer in a subject, whatever the case and behind "AW:" or "Re:"; ``None`` if there is none."""
    match = _TAG.search(subject or "")
    if match is None:
        return None
    return AnswerTag(token=match.group(1).lower(), accept=match.group(2).upper() == ACCEPT_CODE)


# --- Where the answers go ---------------------------------------------------------------------------


def answer_mailbox() -> Mailbox | None:
    """The mailbox the answers by mail go to – one that Rentalars fetches (PER-032).

    The mailbox that sends the request – the system mailbox – if it is a
    mailbox of the correspondence; else the mailbox that sends the
    correspondence. ``None`` if neither is fetched or has an address.
    """
    for mailbox in (system_mailbox(), outgoing_mailbox()):
        if mailbox is not None and mailbox.for_correspondence and mailbox.can_fetch and mailbox.address:
            return mailbox
    return None


def answers_by_mail(mail_settings: MailSettings | None = None) -> Mailbox | None:
    """The mailbox for answers if the setting asks for answers by mail; ``None``: the request carries the link only."""
    mode = (mail_settings or MailSettings.load()).crew_answers
    return None if mode == CrewAnswerMode.LINK else answer_mailbox()


def mailbox_for_request(line: CrewLine) -> Mailbox | None:
    """The mailbox for the answers if this request goes as a mail with buttons, else ``None`` (PER-032).

    It does if answers by mail are on and a mailbox can take them, and the
    person is active and has an address. A person with an account who
    switched the mails of deployment requests off gets none: the request
    stays in the application, as with the link (UIX-005).
    """
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import preference

    person = line.person
    if person is None or not person.is_active or not person.email:
        return None
    mailbox = answers_by_mail()
    if mailbox is None:
        return None
    account = getattr(person, "user", None)
    if account is not None and account.is_active and not preference(account, Kind.DEPLOYMENT_REQUEST)[1]:
        return None
    return mailbox


# --- The request mail ---------------------------------------------------------------------------------


def _moment(value: Any, pattern: str = "D d.m.Y H:i") -> str:
    """A moment in local time, with the weekday in the language of the installation."""
    return formats.date_format(timezone.localtime(value), local_pattern(pattern))  # UIX-029


def deployment_text(line: CrewLine) -> str:
    """``2027-0001 Stadtfest als Tontechnik, Mi 10.03.2027 08:00 – Fr 12.03.2027 00:00``."""
    return _("%(project)s as %(function)s, %(start)s – %(end)s") % {
        "project": line.project,
        "function": line.job_function.name,
        "start": _moment(line.start),
        "end": _moment(line.end),
    }


def _offer_link(line: CrewLine) -> str:
    """The address where a freelancer makes a price offer for the request (PER-038); empty if that is off.

    The offer needs the application: the person must be able to log in.
    """
    from rentalars.personnel import offers

    account = getattr(line.person, "user", None)
    if account is None or not account.is_active or not account.has_usable_password():
        return ""
    if not offers.person_may_offer(line.person):
        return ""
    return f"{settings.RENTALARS_URL}{reverse('personnel:offer_make', args=[line.project, line.pk])}"


def short_deployment(line: CrewLine) -> str:
    """``Stadtfest, Mi 10.03.`` – for subjects."""
    return f"{line.project.name}, {_moment(line.start, 'D d.m.')}"


def mailto(address: str, subject: str, body: str) -> str:
    """A ``mailto:`` link with subject and text, encoded as RFC 6068 asks: UTF-8, ``%20`` and ``%0D%0A``."""
    text = body.replace("\r\n", "\n").replace("\n", "\r\n")
    return f"mailto:{quote(address, safe='@')}?subject={quote(subject, safe='')}&body={quote(text, safe='')}"


def note_label() -> str:
    """The label in the prepared mail behind which the note is written."""
    return pgettext("crew answer mail", "Note:")


def answer_subject(line: CrewLine, token: str, *, accept: bool) -> str:
    """``Zusage: Stadtfest, Mi 10.03. [RA-E-…-JA]`` – the subject of the prepared mail."""
    values = {"deployment": short_deployment(line), "tag": tag_for(token, accept=accept)}
    if accept:
        return _("Acceptance: %(deployment)s %(tag)s") % values
    return _("Refusal: %(deployment)s %(tag)s") % values


def answer_body(line: CrewLine, *, accept: bool) -> str:
    """The text of the prepared mail: a line for the note, then what it answers."""
    values = {"deployment": deployment_text(line)}
    what = _("Acceptance for: %(deployment)s") if accept else _("Refusal for: %(deployment)s")
    return "\n".join(
        [
            f"{note_label()} ",
            "",
            "----",
            what % values,
            _("Please leave the subject as it is: Rentalars recognises your answer by the code in square brackets."),
        ]
    )


def _name_of(user: Any) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def request_message(
    line: CrewLine,
    request_mail: CrewRequestMail,
    mailbox: Mailbox,
    *,
    with_link: bool,
    previous: tuple[Any, Any] | None = None,
) -> EmailMultiAlternatives:
    """The request mail: what, when, where – and the buttons "Accept" and "Decline" (PER-032).

    Args:
        line: The crew line asked for, with its person.
        request_mail: The stored request with the token.
        mailbox: The mailbox the answers go to.
        with_link: Also the link into Rentalars ("both").
        previous: The period asked for before, if the person is asked again
            for new times (PER-034): the mail says "New times" and names the
            former ones.
    """
    from rentalars.core.models import CompanyProfile

    person = line.person
    project = line.project
    account = getattr(person, "user", None)
    token = request_mail.token
    context = {
        "name": person.first_name or person.name,
        "project_label": str(project),
        "function": line.job_function.name,
        "period": f"{_moment(line.start)} – {_moment(line.end)}",
        "venue": project.venue_label,
        "meeting_point": line.meeting_point,
        "note": line.note,
        "asked_by": _name_of(line.requested_by) or _name_of(project.manager),
        "accept_url": mailto(mailbox.address, answer_subject(line, token, accept=True), answer_body(line, accept=True)),
        "decline_url": mailto(
            mailbox.address, answer_subject(line, token, accept=False), answer_body(line, accept=False)
        ),
        "address": mailbox.address,
        "link": f"{settings.RENTALARS_URL}{reverse('projects:deployment', args=[project])}" if with_link else "",
        "company_name": CompanyProfile.load().name,
        # The notifications can be switched off by who can log in (UIX-005).
        "can_switch_off": account is not None and account.is_active and account.has_usable_password(),
        # PER-038: where a freelancer can name their own price – only if the company switched that on.
        "offer_link": _offer_link(line),
        "language": translation.get_language() or settings.LANGUAGE_CODE,
        # PER-034: asked again because the times changed.
        "previous_period": f"{_moment(previous[0])} – {_moment(previous[1])}" if previous else "",
    }
    if previous:
        subject = "[Rentalars] " + _("Deployment request with new times: %(deployment)s") % {
            "deployment": deployment_text(line)
        }
    else:
        subject = "[Rentalars] " + _("Deployment request: %(deployment)s") % {"deployment": deployment_text(line)}
    context["subject"] = subject
    message = EmailMultiAlternatives(
        subject,
        render_to_string("mail/email/crew_request.txt", context),
        None,
        [person.email],
        reply_to=[mailbox.address],
        headers={"Auto-Submitted": "auto-generated"},
    )
    message.attach_alternative(render_to_string("mail/email/crew_request.html", context), "text/html")
    return message


def send_request_mail(line: CrewLine, mailbox: Mailbox, *, previous: tuple[Any, Any] | None = None) -> CrewRequestMail:
    """Store the request with a new token and send its mail once the request is committed (PER-032).

    The mail goes the way of the system mails – through the system mailbox
    or the server of the configuration – and is noted in the mail log
    (EML-039). A failure is logged, never raised: the request stands, as
    with a notification whose mail failed. ``previous``: the times asked
    for before, when the person is asked again for new ones (PER-034).
    """
    request_mail = CrewRequestMail.objects.create(
        token=new_token(),
        line=line,
        person=line.person,
        sent_to=(line.person.email or "").strip().lower(),
        requested_at=line.requested_at,
    )
    with_link = MailSettings.load().crew_answers == CrewAnswerMode.BOTH
    # UIX-029: in the language of the person asked – the footer is added on sending, so that too.
    account = getattr(line.person, "user", None)
    with for_user(account) as language:
        message = request_message(line, request_mail, mailbox, with_link=with_link, previous=previous)
    transaction.on_commit(lambda: _send(message, language))
    return request_mail


def _send(message: EmailMessage, language: str | None = None) -> None:
    try:
        with translation.override(language or translation.get_language()):
            message.send()
    except Exception:
        logger.warning("The mail “%s” to %s could not be sent.", message.subject, message.to, exc_info=True)


# --- The answer ---------------------------------------------------------------------------------------------


def note_of(parsed: ParsedMail) -> str:
    """The note of an answer: what is written behind "Note:" up to the line of dashes (PER-032).

    Quoted mails and the signature are left out. Without the label there is
    no note – the text of a mail is not guessed at.
    """
    text = parsed.text or html_to_text(parsed.html)
    new, _rest = split_quoted(text)
    lines = new.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    labels = {label.strip().rstrip(":").strip().lower() for label in (note_label(), "Anmerkung:", "Note:")}
    for index, line in enumerate(lines):
        head, colon, rest = line.partition(":")
        if not colon or head.strip().lower() not in labels:
            continue
        collected = [rest]
        for following in lines[index + 1 :]:
            if _NOTE_END.match(following):
                break
            collected.append(following)
        return " ".join(" ".join(collected).split())[:NOTE_MAX_LENGTH]
    return ""


def refusal_reason(request_mail: CrewRequestMail, line: CrewLine | None) -> str:
    """Why an answer to this request cannot be taken over now; empty if it can (PER-032, PER-016).

    It mirrors the answer in the browser: only the person asked answers (the
    token stands for them), only while the request waits, and not in a
    closed project (PRJ-009). In addition an answer by mail is refused for a
    cancelled project and after the end of the deployment – the browser no
    longer offers those requests on the start page either.
    """
    from rentalars.projects.models import ProjectStatus, RequestStatus

    if line is None or line.person_id is None or line.person_id != request_mail.person_id:
        return WITHDRAWN
    if line.request_status == RequestStatus.NONE or line.requested_at is None:
        return WITHDRAWN
    # Asked again: a later time of the request, or – asked twice within the same moment – a later request mail.
    newer_mail = CrewRequestMail.objects.filter(line_id=line.pk, pk__gt=request_mail.pk).exists()
    if line.requested_at != request_mail.requested_at or newer_mail:
        if line.requested_at < request_mail.requested_at:
            return WITHDRAWN
        return REPLACED if line.request_status == RequestStatus.REQUESTED else ANSWERED
    if line.project.status in (ProjectStatus.CANCELLED, ProjectStatus.CLOSED):
        return CANCELLED
    if line.request_status != RequestStatus.REQUESTED:
        return ANSWERED
    if not line.person.is_active:
        return WITHDRAWN
    if line.end < timezone.now():
        return EXPIRED
    return ""


def asked_address(request_mail: CrewRequestMail) -> str:
    """The address the request mail went to, lower-case; for older requests the address of the person now."""
    person = request_mail.person
    return (request_mail.sent_to or (person.email if person is not None else "")).strip().lower()


#: A DMARC verdict "fail" in an ``Authentication-Results`` header (RFC 8601): ``dmarc=fail``, with blanks allowed.
_DMARC_FAILED = re.compile(r"\bdmarc\s*=\s*fail\b", re.IGNORECASE)


def _comparable(address: str) -> str:
    """An address as it is compared: lower-case, the domain in its ASCII form (``müller.example`` is ``xn--mller-kva.example``)."""
    local, at, domain = unicodedata.normalize("NFC", address.strip()).lower().rpartition("@")
    if not at or not local or not domain:
        return ""
    # Label by label with punycode and nothing else: the "idna" codec would map full-width letters to plain ones
    # (NFKC), so that ``ｇｍａｉｌ.com`` would be taken for ``gmail.com`` – a domain the mail server never checked.
    labels = []
    for label in domain.split("."):
        if label.isascii():
            labels.append(label)
            continue
        try:
            labels.append("xn--" + label.encode("punycode").decode("ascii"))
        except UnicodeError:
            labels.append(label)
    return f"{local}@{'.'.join(labels)}"


def sender_reason(request_mail: CrewRequestMail, parsed: ParsedMail) -> str:
    """Why the sender of an answer does not count; empty if it does (PER-032).

    Only the address the request was sent to answers it: a forwarded request
    must not be answered by whoever got it. Then, if the receiving mail server
    wrote a verdict, a failed DMARC check means the ``From`` is forged.
    """
    # S2: the address of the structured header, not what ``parseaddr`` makes of the line.
    sender = _comparable(parsed.sender_checked)
    asked = _comparable(asked_address(request_mail))
    # A mail with two ``From`` headers: the receiving server may have checked the other one.
    if not sender or not asked or sender != asked or parsed.from_count != 1:
        return SENDER
    if _DMARC_FAILED.search(parsed.authentication):
        return FORGED
    trusted = MailSettings.load().crew_answer_trusted_server.strip()
    if trusted and not confirmed_by(parsed.authentication_headers, trusted, sender):
        return UNCONFIRMED
    return ""


def _results_of(header: str, server: str) -> str:
    """What an ``Authentication-Results`` header says if it comes from ``server`` (its ``authserv-id``), else empty.

    RFC 8601: the header starts with the identifier of the server that wrote it (maybe followed by a version number),
    then a semicolon. A mail that comes in may carry such headers of its own, written by its sender; only the one of
    the own server counts.
    """
    identifier, _semicolon, rest = header.partition(";")
    words = identifier.split()
    return rest if words and words[0].lower() == server.strip().lower() else ""


def _clauses(text: str) -> list[str]:
    """The results of an ``Authentication-Results`` header: comments in parentheses taken out, split at ``;`` outside quotes.

    A field the sender can influence (``smtp.mailfrom="x;dmarc=pass"@evil.example``, or a comment) must not be able to
    start a result of its own.
    """
    clean: list[str] = []
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if escaped:
            escaped = False
            if depth == 0:
                clean.append(character)
            continue
        if character == "\\":
            escaped = True
            if depth == 0:
                clean.append(character)
            continue
        if quoted:
            clean.append(character)
            quoted = character != '"'
            continue
        if character == '"' and depth == 0:
            quoted = True
            clean.append(character)
        elif character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif depth == 0:
            clean.append(character)
    results: list[str] = []
    current: list[str] = []
    quoted = False
    for character in "".join(clean):
        if character == '"':
            quoted = not quoted
        if character == ";" and not quoted:
            results.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    results.append("".join(current).strip())
    return [result for result in results if result]


_RESULT = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)\s*=\s*([A-Za-z]+)")
_PROPERTY = re.compile(r"\b(header\.[a-z]+)\s*=\s*(\"[^\"]*\"|[^\s;]+)", re.IGNORECASE)


def _domain_of(value: str) -> str:
    """The domain in a property such as ``header.d=example.com``, ``header.i=@example.com`` or ``header.from=a@example.com``."""
    domain = value.strip('"').rpartition("@")[2].lower().rstrip(".")
    return _comparable("x@" + domain).rpartition("@")[2]


def _has_result(rest: str, method: str) -> bool:
    """Whether the results hold one of this method (``dmarc``, ``dkim``)."""
    for clause in _clauses(rest):
        match = _RESULT.match(clause)
        if match is not None and match.group(1).lower() == method:
            return True
    return False


def confirmed_by(headers: list[str], server: str, sender: str) -> bool:
    """Whether the mail server ``server`` confirmed the sender: ``dmarc=pass`` for his domain, or ``dkim=pass`` signed by it.

    The sender is an address in the form of :func:`_comparable`. Which headers count: a server prepends its header, so
    the headers of the sender's side stand below it. The topmost header with the name of the server counts – and, when
    that one holds no DMARC result and the server wrote more headers (one per check), those down to the first one with
    a DMARC result. A DMARC pass names the domain it was for (``header.from``), which must be the domain of the sender.
    DKIM counts only if the signing domain (``header.d`` or ``header.i``, at least a name and a top-level domain) is the
    domain of the address or a parent of it – never a different domain.

    A mail server that does not name itself first in the header (Exchange Online starts with ``spf=pass``) cannot be
    used; the answer then goes the way of the link.
    """
    domain = sender.rpartition("@")[2]
    counted: list[str] = []
    for header in headers:
        rest = _results_of(header, server)
        if rest:
            counted.append(rest)
            if _has_result(rest, "dmarc"):
                break
    if counted and not _has_result(counted[-1], "dmarc"):
        counted = counted[:1]  # no DMARC result at all: only the topmost header counts
    for rest in counted:
        for clause in _clauses(rest):
            match = _RESULT.match(clause)
            if match is None or match.group(2).lower() != "pass":
                continue
            method = match.group(1).lower()
            properties = {name.lower(): value for name, value in _PROPERTY.findall(clause)}
            if method == "dmarc":
                named = properties.get("header.from")
                if named is None or _domain_of(named) == domain:
                    return True
            elif method == "dkim":
                signer = properties.get("header.d") or properties.get("header.i")
                name = _domain_of(signer) if signer else ""
                if "." in name and (domain == name or domain.endswith("." + name)):
                    return True
    return False


#: What may stand in the warning mail as the sender: a plain address. Anything else – a quoted display
#: string posing as an address, say – is not repeated, as the warning comes from the trusted system sender.
_PLAIN_ADDRESS = re.compile(r"^[^\s\"<>(),;:\\]{1,120}@[^\s\"<>(),;:\\]{1,120}$")

#: A person is warned about the same refusal of the same request once in this time; a mail flood changes nothing.
WARNING_INTERVAL = timedelta(hours=1)


def shown_sender(address: str) -> str:
    """The sender as the warning mail names it: the plain address, else nothing."""
    address = address.strip().lower()
    return address if _PLAIN_ADDRESS.match(address) else ""


def warned_lately(request_mail: CrewRequestMail, reason: str) -> bool:
    """Whether the person got a warning for this reason about this request within :data:`WARNING_INTERVAL`."""
    return MailLogEntry.objects.filter(
        direction=Direction.INCOMING,
        result=LogResult.CREW_ANSWER,
        subject__icontains=request_mail.token,
        detail__endswith=f":{reason}",
        timestamp__gte=timezone.now() - WARNING_INTERVAL,
    ).exists()


def _record(request_mail: CrewRequestMail, line: CrewLine, *, accept: bool, note: str) -> None:
    """Record the answer as the browser does, acting as the person; note in the history that it came by mail."""
    from rentalars.projects import crew

    person = line.person
    account = getattr(person, "user", None)
    if account is not None and not account.is_active:
        account = None
    with acting_as(account if account is not None else person.name):
        crew.answer_deployment(line, accept=accept, note=note, user=account)
        record_event(line, "crew_line.answered_by_mail", {"person": person.name})
    request_mail.answered_at = timezone.now()
    request_mail.save(update_fields=["answered_at"])


@dataclass
class Outcome:
    """What became of an answer: the detail for the mail log and the project it belongs to."""

    detail: str
    project: Any = None


def _answer(request_mail: CrewRequestMail, tag: AnswerTag, parsed: ParsedMail) -> Outcome:
    """Take an answer over – or tell the person why not – and reply (PER-032)."""
    from rentalars.projects.models import CrewLine

    answer = "accepted" if tag.accept else "declined"
    note = note_of(parsed)
    sender = shown_sender(parsed.sender_address)
    line = None
    try:
        with transaction.atomic():
            line = CrewLine.objects.select_for_update().filter(pk=request_mail.line_id).first()
            reason = sender_reason(request_mail, parsed) or refusal_reason(request_mail, line)
            if not reason:
                _record(request_mail, line, accept=tag.accept, note=note)
    except ValidationError:
        # The service refused after all; nothing was changed. The mail must not block the fetch.
        reason = WITHDRAWN
    person = line.person if line is not None and line.person_id == request_mail.person_id else request_mail.person
    reply = None
    if not (reason and warned_lately(request_mail, reason)):
        reply = reply_message(
            person,
            line,
            accept=tag.accept,
            reason=reason,
            note=note,
            sender=sender,
            in_reply_to=parsed.message_id,
        )
    if reply is not None:
        language = translation.get_language()
        transaction.on_commit(lambda: _send(reply, language))
    return Outcome(
        detail=f"{answer}:{reason}" if reason else answer, project=line.project if line is not None else None
    )


def take_answer(box: MailboxConnection, uid: int, size: int, headers: Headers, mailbox: Mailbox) -> bool:
    """Deal with a mail of the fetch if it answers a deployment request (PER-032).

    Called for every mail of every mailbox before the project tag and the
    inquiries are looked at (``mail.fetching``).

    Returns:
        ``True`` if the mail was an answer and is dealt with; ``False`` for a
        normal mail – no tag, an unknown token, or an automatic reply.

    Raises:
        MailboxError: The mailbox failed; nothing was recorded, the next fetch tries again.
    """
    tag = find_tag(headers.subject)
    if tag is None:
        return False
    request_mail = CrewRequestMail.objects.filter(token=tag.token).first()
    if request_mail is None:
        return False
    if MailLogEntry.objects.filter(
        direction=Direction.INCOMING, result=LogResult.CREW_ANSWER, message_key=headers.key
    ).exists():
        # Dealt with before: filing it away failed then, or it came into a second mailbox too.
        box.file_away(uid, answer=True)
        return True
    parsed = parse_mail(box.fetch(uid, limit=TEXT_LIMIT if size > TEXT_LIMIT else None))
    if parsed.kind != MailKind.NORMAL:
        # An out-of-office reply or a bounce that quotes the tag answers nothing, and gets no reply.
        return False
    # UIX-029: the reply in the language of the person who answered.
    with for_user(getattr(request_mail.person, "user", None)):
        outcome = _answer(request_mail, tag, parsed)
    log.record_incoming(
        result=LogResult.CREW_ANSWER,
        sender=headers.sender,
        recipients=headers.to,
        subject=headers.subject,
        message_key=headers.key,
        mailbox=mailbox,
        project=outcome.project,
        detail=outcome.detail,
    )
    box.file_away(uid, answer=True)
    return True


# --- The reply to the person -------------------------------------------------------------------------


def _reason_text(reason: str, line: CrewLine | None, sender: str = "") -> str:
    from rentalars.projects.models import RequestStatus

    if reason == ANSWERED and line is not None:
        # PER-041: planned firmly in the meantime counts like accepted.
        accepted = line.request_status in (RequestStatus.ACCEPTED, RequestStatus.FIRM)
        answer = CREW_ANSWER_DETAILS["accepted" if accepted else "declined"]
        return _("This request was answered already: %(answer)s.") % {"answer": capfirst(str(answer))}
    if reason == SENDER:
        return _(
            "The answer did not come from the address this request was sent to, but from %(sender)s. "
            "Only a mail from your own address counts: please answer from there, or in Rentalars. "
            "If you did not send it, somebody may have got your request mail forwarded."
        ) % {"sender": sender or "–"}
    return str(
        {
            FORGED: _(
                "The check of the sender of the answer by the mail server failed; the sender address looks forged. "
                "Please answer again, or in Rentalars."
            ),
            UNCONFIRMED: _(
                "The mail server did not confirm who sent the answer (no DMARC or DKIM pass for the sender). "
                "An answer by mail counts only when it is confirmed: please answer in Rentalars."
            ),
            EXPIRED: _("The deployment is over."),
            REPLACED: _(
                "There is a newer request for this deployment. Please answer with the buttons of the newest mail."
            ),
            CANCELLED: _("The project was cancelled or closed."),
        }.get(reason, _("The request no longer holds: it was withdrawn, or somebody else is planned now."))
    )


def reply_message(
    person: Any,
    line: CrewLine | None,
    *,
    accept: bool,
    reason: str,
    note: str,
    sender: str,
    in_reply_to: str = "",
) -> EmailMessage | None:
    """The short mail to the person: the answer arrived – or why it was not taken over (PER-032).

    It goes to the address Rentalars knows for the person, never to an
    unknown sender, and carries no tag: an automatic reply to it is no
    answer again. ``None`` if the person has no address.
    """
    address = getattr(person, "email", "") if person is not None else ""
    if not address:
        return None
    planner = ""
    if line is not None:
        planner = _name_of(line.requested_by) or _name_of(line.project.manager)
    planner = planner or _("the planning")
    deployment = deployment_text(line) if line is not None else ""
    short = short_deployment(line) if line is not None else ""
    lines = [_("Hello %(name)s,") % {"name": person.first_name or person.name}, ""]
    if not reason:
        if accept:
            subject = _("Your acceptance has arrived: %(deployment)s") % {"deployment": short}
            lines.append(
                _("your acceptance for %(deployment)s has arrived and was passed on to %(planner)s. Thank you!")
                % {"deployment": deployment, "planner": planner}
            )
            # PER-042: "available" entered where the own calendar said "not available".
            if line is not None and getattr(line, "marked_available", None) is not None:
                from rentalars.projects.crew import available_text

                lines += ["", available_text(line)]
        else:
            subject = _("Your refusal has arrived: %(deployment)s") % {"deployment": short}
            lines.append(
                _("your refusal for %(deployment)s has arrived and was passed on to %(planner)s.")
                % {"deployment": deployment, "planner": planner}
            )
        if note:
            lines += ["", _("Your note: “%(note)s”") % {"note": note}]
    else:
        if short:
            subject = _("Your answer was not taken over: %(deployment)s") % {"deployment": short}
            lines.append(_("your answer for %(deployment)s was not taken over.") % {"deployment": deployment})
        else:
            subject = _("Your answer to a deployment request was not taken over")
            lines.append(_("your answer to a deployment request was not taken over."))
        lines += [
            _reason_text(reason, line, sender),
            "",
            _("Nothing was changed. If you have questions, please contact %(planner)s.") % {"planner": planner},
        ]
    # EML-045: that Rentalars sent it, for which company, says the footer of every system mail.
    headers = {"Auto-Submitted": "auto-replied"}
    if in_reply_to:
        headers.update({"In-Reply-To": in_reply_to, "References": in_reply_to})
    return EmailMessage(f"[Rentalars] {subject}", "\n".join(lines) + "\n", None, [address], headers=headers)
