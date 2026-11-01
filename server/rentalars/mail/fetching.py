# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetching mails and assigning them to projects (EML-005 to EML-018, EML-023, EML-032, EML-041).

Every active mailbox of the correspondence is fetched, one after the other
(EML-041). A mailbox that fails does not stop the others; each keeps the
state of its own fetch. One fetch of a mailbox, step by step:

1. Look at the headers of the mails that arrived since the last fetch.
   Nothing in the mailbox changes by that, not even the read state.
2. Decide per mail:

   * an **answer to a deployment request** by reply mail – a tag
     ``[RA-E-…]`` with a known token – is recorded first, whatever the
     mailbox does with mails without tag (PER-032, ``mail.crew_answers``);
   * a **tag** in the subject names a project → assign (EML-008);
   * a tag that names **no** project → leave the mail alone and put it on
     the list under Projects → Inquiries (EML-014, EML-042);
   * no tag, but a **reply** to a mail already assigned (``In-Reply-To`` or
     ``References``) → assign to that project (EML-012);
   * anything else → an **inquiry** if the mailbox takes in mails without
     tag – it waits in the inbox and on the same list (EML-041), and an
     automation may answer it (ADM-013, ``automations.engine``) –, else
     leave alone; it never shows up in Rentalars (EML-013). EML-047:
     a further address of the mailbox (alias) the mail went to has a rule
     of its own – leave alone, inquiry, or a **service case** made at once
     with the mail in it (``mail.aliases``). EML-049: only mails
     that arrived from the point in time set with that rule on – optionally
     only unread ones – are taken in; the others are left alone.

3. An assigned mail is read completely and stored with its attachments;
   only then does the mailbox do what it is set to do with assigned mails:
   mark as read and move away, delete, or leave unchanged (EML-006,
   EML-041). A mail already stored – recognised by its Message-ID – is not
   stored twice (EML-007); if moving it failed last time, it is moved now.
4. The project manager is notified (EML-023); for a closed or cancelled
   project with a note saying so (EML-018).

Problems – wrong password, server not reachable – are recorded per mailbox
with time and text, reported to the operators once until the next
successful fetch, and shown in the settings and the self-check (EML-032).

Every mail looked at is noted in the mail log with what became of it and
the mailbox it came from: assigned, unknown tag, inquiry, left in the inbox
– or failed (EML-039, EML-041).

Only one fetch runs at a time; a second one started meanwhile (the timer and
the button "fetch now") returns at once.
"""

from __future__ import annotations

import datetime
import fcntl
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.crypto import SecretUnreadableError
from rentalars.core.i18n import LazyCall, LocalText, format_date
from rentalars.core.uploads import document_type_allowed
from rentalars.mail import log
from rentalars.mail.aliases import alias_for, untagged_rule, untagged_skip
from rentalars.mail.crew_answers import take_answer
from rentalars.mail.imap import Mailbox as MailboxConnection
from rentalars.mail.imap import MailboxError, open_mailbox
from rentalars.mail.locks import answers_locked, default_lock
from rentalars.mail.mailboxes import correspondence_mailboxes, legacy_mailbox
from rentalars.mail.models import (
    AssignedBy,
    LogResult,
    MailAttachment,
    Mailbox,
    MailboxAddress,
    MailSettings,
    ProjectMail,
    UnknownTagMail,
    Untagged,
)
from rentalars.mail.parsing import Headers, ParsedMail, parse_headers, parse_mail
from rentalars.mail.suppliers import mail_addresses, supplier_for
from rentalars.mail.tags import find_numbers
from rentalars.projects.models import FINISHED_STATUSES, Project, ProjectStatus

logger = logging.getLogger(__name__)

#: How much of a mail above the size limit is read: enough for its text.
TEXT_OF_LARGE_MAIL = 512 * 1024


@dataclass
class FetchResult:
    """What a fetch did, for the page, the command and the tests.

    The result of a whole fetch adds up the results of its mailboxes, which
    are kept in ``mailboxes`` (EML-041); ``error`` names the mailbox of each
    problem.
    """

    looked_at: int = 0
    imported: list[ProjectMail] = field(default_factory=list)
    unknown: list[UnknownTagMail] = field(default_factory=list)
    inquiries: list[UnknownTagMail] = field(default_factory=list)
    skipped: str = ""
    error: str = ""
    mailbox: Mailbox | None = None
    mailboxes: list[FetchResult] = field(default_factory=list)
    #: PER-032: answers to deployment requests by reply mail.
    crew_answers: int = 0

    @property
    def ok(self) -> bool:
        """Whether the fetch ran without a problem."""
        return not self.error and not self.skipped

    def add(self, part: FetchResult) -> None:
        """Add the result of one mailbox."""
        self.mailboxes.append(part)
        self.looked_at += part.looked_at
        self.imported += part.imported
        self.unknown += part.unknown
        self.inquiries += part.inquiries
        self.crew_answers += part.crew_answers
        if part.error:
            text = f"{part.mailbox}: {part.error}" if part.mailbox is not None else part.error
            self.error = f"{self.error}\n{text}" if self.error else text


@contextmanager
def _only_one_fetch() -> Iterator[bool]:
    """A lock in the data folder: yields ``False`` if another fetch is running."""
    path = Path(settings.DATA_DIR) / "mail-fetch.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def fetch_is_due(
    mailbox: Mailbox, now: datetime.datetime | None = None, *, interval_minutes: int | None = None
) -> bool:
    """Whether the interval since the last fetch of a mailbox is over (EML-005).

    The interval holds for all mailboxes (``MailSettings.interval_minutes``).
    """
    if mailbox.last_fetch_at is None:
        return True
    if interval_minutes is None:
        interval_minutes = MailSettings.load().interval_minutes
    now = now or timezone.now()
    # A few seconds of slack: the timer fires every minute, not on the second.
    return now - mailbox.last_fetch_at >= datetime.timedelta(minutes=interval_minutes, seconds=-10)


def fetch_mail(*, force: bool = False, opener: Callable[[Mailbox], Any] | None = None) -> FetchResult:
    """Fetch new mails from every active mailbox of the correspondence (EML-005, EML-041).

    The mailboxes are fetched one after the other; a mailbox that fails does
    not stop the others.

    Args:
        force: Fetch even if the interval is not over ("fetch now").
        opener: Opens a mailbox; the tests pass a mailbox in memory.
    """
    opener = opener or open_mailbox
    rules = MailSettings.load()
    mailboxes = [mailbox for mailbox in correspondence_mailboxes() if mailbox.can_fetch]
    if not mailboxes:
        return FetchResult(skipped=_("No mailbox of the correspondence is set up and switched on."))
    due = [mailbox for mailbox in mailboxes if force or fetch_is_due(mailbox, interval_minutes=rules.interval_minutes)]
    if not due:
        return FetchResult(skipped=_("Not due yet."))
    with _only_one_fetch() as mine:
        if not mine:
            return FetchResult(skipped=_("A fetch is running already."))
        result = FetchResult()
        for mailbox in due:
            result.add(_fetch_mailbox(mailbox, opener, rules))
        return result


def _fetch_mailbox(mailbox: Mailbox, opener: Callable[[Mailbox], Any], rules: MailSettings) -> FetchResult:
    """Fetch one mailbox and record how it went (EML-032, EML-041); never raises."""
    result = FetchResult(mailbox=mailbox)
    Mailbox.objects.filter(pk=mailbox.pk).update(last_fetch_at=timezone.now())
    try:
        with opener(mailbox) as box:
            _fetch_new(box, mailbox, rules, result)
    except MailboxError as error:
        result.error = str(error)
    except SecretUnreadableError:
        result.error = _("The stored password cannot be read any more. Enter it again.")
    except Exception as error:
        logger.exception("Fetching the mails of %s failed.", mailbox)
        result.error = _("Unexpected error: %(error)s") % {"error": error}
    _record_outcome(mailbox, result)
    return result


def _fetch_new(box: MailboxConnection, mailbox: Mailbox, rules: MailSettings, result: FetchResult) -> None:
    validity = box.select_inbox()
    after = mailbox.last_uid if validity and validity == mailbox.uid_validity else 0
    last_done = after
    blocked = False
    for info in box.headers_after(after):
        if info.deleted:
            if not blocked:
                last_done = info.uid
            continue
        result.looked_at += 1
        headers = parse_headers(info.header)
        try:
            _handle(box, info.uid, info.size, headers, mailbox, rules, result, seen=info.seen, received=info.received)
        except MailboxError as error:
            # The mail stays where it is; the next fetch starts from here and tries again.
            logger.warning("Mail %s of %s could not be dealt with: %s", info.uid, mailbox, error)
            blocked = True
            result.error = str(error)
            _note(headers, LogResult.FAILED, mailbox=mailbox, detail=str(error))
            continue
        if not blocked:
            last_done = info.uid
    Mailbox.objects.filter(pk=mailbox.pk).update(uid_validity=validity, last_uid=last_done)


def _note(headers: Headers, result: str, **extra: Any) -> None:
    """Note a mail of the fetch in the mail log, with its mailbox (EML-039, EML-041)."""
    log.record_incoming(
        result=result,
        sender=headers.sender,
        recipients=headers.to,
        subject=headers.subject,
        message_key=headers.key,
        **extra,
    )


def project_for_headers(headers: Headers) -> tuple[Project | None, str, str]:
    """Decide where a mail belongs: ``(project, how, unknown tag)`` (EML-008, EML-012, EML-014)."""
    numbers = find_numbers(headers.subject)
    if numbers:
        # EML-016 (later stage): with several tags the first one counts.
        project = Project.objects.filter(number__iexact=numbers[0]).first()
        if project is None:
            return None, "", numbers[0]
        return project, AssignedBy.TAG, ""
    references = headers.referenced_keys
    if references:
        earlier = (
            ProjectMail.objects.filter(message_key__in=references).select_related("project").order_by("-date").first()
        )
        if earlier is not None:
            return earlier.project, AssignedBy.REFERENCE, ""
    return None, "", ""


def _waiting(headers: Headers, uid: int, mailbox: Mailbox, tag: str) -> UnknownTagMail:
    """Note a mail that waits in the inbox to be taken over by hand (EML-014, EML-041).

    EML-047: with the address of the mailbox it went to – a listed alias, else the mailbox's own address.
    """
    alias = alias_for(mailbox, headers)
    waiting, _created = UnknownTagMail.objects.update_or_create(
        message_key=headers.key,
        defaults={
            "message_id": headers.message_id,
            "uid": uid,
            "subject": headers.subject[:500],
            "sender": headers.sender[:300],
            "date": headers.date,
            "tag": tag[:120],
            "mailbox": mailbox,
            "address": (alias.address if alias is not None else mailbox.address)[:254],
        },
    )
    return waiting


def _handle(
    box: MailboxConnection,
    uid: int,
    size: int,
    headers: Headers,
    mailbox: Mailbox,
    rules: MailSettings,
    result: FetchResult,
    *,
    seen: bool = False,
    received: datetime.datetime | None = None,
) -> None:
    existing = ProjectMail.objects.filter(message_key=headers.key).first()
    if existing is not None:
        # Stored before (EML-007), but still in the inbox: moving it failed last time –
        # or the same mail came into a second mailbox; there it is filed away too.
        box.file_away(uid)
        return
    # PER-032: an answer to a deployment request by reply mail – in every mailbox, before tags and inquiries.
    if take_answer(box, uid, size, headers, mailbox):
        result.crew_answers += 1
        return
    project, how, unknown_tag = project_for_headers(headers)
    if unknown_tag:
        result.unknown.append(_waiting(headers, uid, mailbox, unknown_tag))
        _note(headers, LogResult.UNKNOWN_TAG, mailbox=mailbox, detail=unknown_tag)
        return
    if project is None:
        # EML-047: the address the mail went to decides – a listed alias by its own rule, else the mailbox.
        rule, alias = untagged_rule(mailbox, headers)
        address = alias.address if alias is not None else ""
        if rule == Untagged.IGNORE:
            _note(headers, LogResult.LEFT_IN_INBOX, mailbox=mailbox, detail=address)
            return  # EML-013: not ours; it stays in the inbox as it is.
        # EML-049: only mails that arrived from the point in time of the address (or mailbox) on, and – if so
        # set – only unread ones; the others stay in the inbox as they are. The arrival in the mailbox
        # (INTERNALDATE) counts, else the Date header.
        skip = untagged_skip(alias if alias is not None else mailbox, received=received or headers.date, seen=seen)
        if skip:
            _note(headers, LogResult.LEFT_IN_INBOX, mailbox=mailbox, detail=f"{skip}:{address}" if address else skip)
            return
        # EML-041: an inquiry; it waits in the inbox until somebody takes it over.
        waiting = _waiting(headers, uid, mailbox, "")
        case = None
        if rule == Untagged.SERVICE_CASE and alias is not None:
            case = _new_case(box, uid, size, headers, waiting, mailbox, alias, rules, result)
        if case is None:
            result.inquiries.append(waiting)
            _note(headers, LogResult.INQUIRY, mailbox=mailbox, detail=address)
        # ADM-013: automations of the trigger "mail without project tag", e.g. a confirmation of receipt –
        # also for a mail that became a service case at once (EML-047).
        from rentalars.automations.engine import inquiry_arrived

        inquiry_arrived(waiting, headers, mailbox, project=case, address=address)
        return
    too_large = size > rules.max_message_bytes
    raw = box.fetch(uid, limit=TEXT_OF_LARGE_MAIL if too_large else None)
    mail = import_mail(raw, project, assigned_by=how, size=size, too_large=too_large, mailbox=mailbox)
    box.file_away(uid)
    result.imported.append(mail)
    _note(headers, LogResult.ASSIGNED, mailbox=mailbox, project=project, mail=mail, detail=how)
    announce(mail)


def _new_case(
    box: MailboxConnection,
    uid: int,
    size: int,
    headers: Headers,
    waiting: UnknownTagMail,
    mailbox: Mailbox,
    alias: MailboxAddress,
    rules: MailSettings,
    result: FetchResult,
) -> Project | None:
    """Make a service case of a mail without tag to an address set up so, with the mail in it (EML-047, PRJ-090).

    The case is named after the subject; the customer and contact come from
    the sender's address as for "Als Servicefall anlegen" under Anfragen
    (``projects.service_cases.suggestions_from_inquiry``); the person named
    with the address is responsible and is told. Case and mail are stored
    together or not at all: if that fails, the mail waits as an inquiry.
    """
    from rentalars.projects import service_cases

    fields = service_cases.suggestions_from_inquiry(waiting)
    manager = alias.case_manager if alias.case_manager_id and alias.case_manager.is_active else None
    if manager is not None:
        fields["manager"] = manager
    too_large = size > rules.max_message_bytes
    raw = box.fetch(uid, limit=TEXT_OF_LARGE_MAIL if too_large else None)
    try:
        with transaction.atomic():
            # The notification below replaces the one of a new case ("is yours now").
            case = service_cases.create_case(user=manager, **fields)
            mail = import_mail(
                raw, case, assigned_by=AssignedBy.NEW_CASE, size=size, too_large=too_large, mailbox=mailbox
            )
    except ValidationError as error:
        logger.warning("No service case could be made of a mail to %s: %s", alias.address, error)
        return None
    box.file_away(uid)
    waiting.resolved_at = timezone.now()
    waiting.save(update_fields=["resolved_at"])
    result.imported.append(mail)
    _note(headers, LogResult.ASSIGNED, mailbox=mailbox, project=case, mail=mail, detail=AssignedBy.NEW_CASE)
    if manager is not None:
        from rentalars.notifications.models import Kind
        from rentalars.notifications.services import notify

        notify(
            [manager],
            Kind.NEW_MAIL,
            # UIX-029: in the language of the one responsible.
            LocalText(
                gettext_lazy("New service case %(number)s from a mail to %(address)s: %(subject)s"),
                number=case.number,
                address=alias.address,
                subject=mail.subject,
            ),
            body=LocalText(gettext_lazy("From %(sender)s"), sender=mail.sender_label),
            url=reverse("projects:case_detail", args=[case]),
            project=case,
        )
    return case


@transaction.atomic
def import_mail(
    raw: bytes,
    project: Project,
    *,
    assigned_by: str,
    size: int = 0,
    too_large: bool = False,
    mailbox: Mailbox | None = None,
) -> ProjectMail:
    """Store a mail with its attachments in a project, noting its mailbox (EML-019, EML-020, EML-028, EML-041)."""
    parsed = parse_mail(raw)
    key = parsed.key
    existing = ProjectMail.objects.filter(message_key=key).first()
    if existing is not None:
        return existing
    mail = ProjectMail(
        project=project,
        message_key=key,
        message_id=parsed.message_id or parsed.fallback_id,
        in_reply_to=parsed.in_reply_to,
        references=parsed.references,
        subject=parsed.subject[:500],
        sender_name=parsed.sender_name,
        sender_address=parsed.sender_address,
        to_addresses=parsed.to,
        cc_addresses=parsed.cc,
        date=parsed.date or timezone.now(),
        text_body=parsed.text,
        html_body=parsed.html,
        kind=parsed.kind,
        assigned_by=assigned_by,
        project_was_finished=project.status in FINISHED_STATUSES,
        size=size or len(raw),
        mailbox=mailbox,
        # EML-055: as the mail settings say – in projects with lock, in service cases open; an answer to a
        # message with lock of the project (In-Reply-To, References) with lock, as it may quote that message.
        locked=default_lock(project) or answers_locked(project, parsed.referenced_keys),
    )
    # PRJ-106: from or to a supplier of subrentals – the mail belongs to that supplier's subrentals.
    mail.supplier = supplier_for(mail_addresses(mail))
    notes = []
    if too_large:
        notes.append(
            _("The mail is larger than %(megabytes)d MB; its attachments were left in the mailbox.")
            % {"megabytes": MailSettings.load().max_message_mb}
        )
    mail.save()
    if not too_large:
        notes += store_attachments(mail, parsed)
    if notes:
        mail.attachments_note = "\n".join(notes)
        mail.save(update_fields=["attachments_note"])
    return mail


def store_attachments(mail: ProjectMail, parsed: ParsedMail) -> list[str]:
    """Store the attachments that the rules for uploads allow (NFA-007); return notes on the others."""
    notes = []
    limit = MailSettings.load().max_message_bytes
    for attachment in parsed.attachments:
        if not document_type_allowed(attachment.filename) and not attachment.is_inline:
            notes.append(
                _("“%(name)s” was not taken over: files of this type are not stored.") % {"name": attachment.filename}
            )
            continue
        if attachment.is_inline and not attachment.content_type.startswith("image/"):
            continue
        if attachment.size > limit:
            notes.append(_("“%(name)s” was not taken over: it is too large.") % {"name": attachment.filename})
            continue
        stored = MailAttachment(
            mail=mail,
            filename=attachment.filename[:255],
            content_type=attachment.content_type[:120],
            size=attachment.size,
            content_id=attachment.content_id[:255],
            is_inline=attachment.is_inline,
        )
        stored.file.save(attachment.filename, ContentFile(attachment.data), save=False)
        stored.save()
    return notes


def announce(mail: ProjectMail) -> None:
    """Tell the project manager about a new mail (EML-023, EML-018).

    EML-055: only those who read the mail are told – a mail with lock (as every mail comes in) only who
    sees prices; an open one the crew of the project as well (``mail.locks``).
    """
    from rentalars.mail.locks import crew_of, readers
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify, project_people

    project = mail.project
    people = project_people(project) + ([] if mail.locked else crew_of(project))
    # UIX-029: written for each recipient in his language.
    if mail.project_was_finished:
        status = ProjectStatus(project.status).label
        title = LocalText(
            gettext_lazy("Mail for the %(status)s project %(project)s: %(subject)s"),
            status=LazyCall(lambda: str(status).lower()),
            project=project,
            subject=mail.subject,
        )
    else:
        title = LocalText(gettext_lazy("New mail for %(project)s: %(subject)s"), project=project, subject=mail.subject)
    notify(
        readers(mail, people),
        Kind.NEW_MAIL,
        title,
        body=LocalText(gettext_lazy("From %(sender)s"), sender=mail.sender_label),
        url=reverse("mail:detail", args=[project, mail.pk]),
        project=project,
    )


def _record_outcome(mailbox: Mailbox, result: FetchResult) -> None:
    """Note success or failure of a mailbox, and report a new problem once (EML-032, EML-041)."""
    now = timezone.now()
    rows = Mailbox.objects.filter(pk=mailbox.pk)
    if not result.error:
        rows.update(last_success_at=now, last_error="", error_reported=False)
        return
    rows.update(last_error=result.error[:2000], last_error_at=now)
    # A warning, not an error: the operators hear of it below, once, as a mail problem.
    logger.warning("Fetching the mails of %s failed: %s", mailbox, result.error)
    current = rows.first()
    if current is None or current.error_reported:
        return
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify, operators

    notify(
        operators(),
        Kind.MAIL_PROBLEM,
        LocalText(
            gettext_lazy("Mails of %(mailbox)s cannot be fetched: %(error)s"), mailbox=current, error=result.error[:150]
        ),
        body=LocalText(
            gettext_lazy("Last successful fetch: %(when)s"),
            when=LazyCall(format_date, timezone.localtime(current.last_success_at), "d.m.Y H:i")
            if current.last_success_at
            else gettext_lazy("never"),
        ),
        url=reverse("mail:settings"),
    )
    rows.update(error_reported=True)


def assign_unknown(
    unknown: UnknownTagMail, project: Project, *, opener: Callable[[Mailbox], Any] | None = None
) -> ProjectMail:
    """Take a waiting mail – unknown tag or inquiry – into a project by hand (EML-014, EML-042).

    The mail is searched in the inbox of its mailbox by its Message-ID, taken
    over and then dealt with like every assigned mail of that mailbox
    (EML-041).

    EML-053: an inquiry noted by hand is no mail – it becomes a note in
    the correspondence of the project (``mail.inquiries.take_manual_into``);
    nothing is fetched.

    Raises:
        MailboxError: The mail is no longer in the inbox, or the mailbox cannot be reached – or the entry is a
            defect report (MAT-057), not a mail.
        ValidationError: An inquiry noted by hand was dealt with already.
    """
    if unknown.is_manual:
        from rentalars.mail.inquiries import take_manual_into

        return take_manual_into(unknown, project)
    if unknown.is_defect:
        raise MailboxError(_("This is a defect report, not a mail. Make a service case of it or take it off the list."))
    mailbox = unknown.mailbox or legacy_mailbox()
    if mailbox is None:
        raise MailboxError(_("The mailbox of this mail is not set up any more."))
    with (opener or open_mailbox)(mailbox) as box:
        box.select_inbox()
        uid = box.find_uid(unknown.message_id) if unknown.message_id else None
        if uid is None:
            raise MailboxError(_("The mail is no longer in the inbox. Forward it with the tag in the subject instead."))
        raw = box.fetch(uid)
        mail = import_mail(raw, project, assigned_by=AssignedBy.MANUAL, size=len(raw), mailbox=mailbox)
        box.file_away(uid)
    unknown.resolved_at = timezone.now()
    unknown.save(update_fields=["resolved_at"])
    log.record_incoming(
        result=LogResult.ASSIGNED,
        sender=mail.sender_label,
        recipients=", ".join(part for part in (mail.to_addresses, mail.cc_addresses) if part),
        subject=mail.subject,
        message_key=mail.message_key,
        project=project,
        mail=mail,
        mailbox=mailbox,
        detail=AssignedBy.MANUAL.value,
    )
    announce(mail)
    return mail


def dismiss_waiting(ids: list[int]) -> int:
    """Take waiting mails off the list under Projekte → Anfragen; they stay in their inboxes (EML-014, PRJ-107).

    Returns:
        How many were taken off; mails dealt with already are left as they are.
    """
    return UnknownTagMail.objects.filter(pk__in=ids, resolved_at__isnull=True).update(resolved_at=timezone.now())
