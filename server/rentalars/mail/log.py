# SPDX-License-Identifier: GPL-3.0-or-later
"""The mail log: every mail that came in or went out (EML-039).

Three places write to it:

* the fetch (``mail.fetching``) – for every mail it looked at: assigned to a
  project, with a tag that names no project, or left in the inbox;
* sending from a project (``mail.sending``) – sent, or failed with the
  error of the mail server;
* ``mail.backends.LoggingEmailBackend`` – every system mail Django sends:
  invitations, password links, notifications, the test mail of the
  self-check.

Writing the log never stops a mail: an entry that cannot be written is
reported to the error log and left out.

Only the envelope is kept – time, addresses, subject, result, the mailbox
it went through (EML-041) – never the text. Old entries are removed by the daily maintenance (:func:`delete_old_entries`).
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from rentalars.mail.models import Direction, LogKind, LogResult, MailLogEntry, MailSettings

logger = logging.getLogger(__name__)

#: How long entries are kept when the mails themselves are kept without limit (EML-039).
DEFAULT_RETENTION_DAYS = 365


def _joined(addresses: Iterable[str] | str) -> str:
    if isinstance(addresses, str):
        return addresses
    return ", ".join(address for address in addresses if address)


def record(
    *,
    direction: str,
    kind: str,
    result: str,
    sender: str = "",
    recipients: Iterable[str] | str = "",
    subject: str = "",
    project: Any = None,
    mail: Any = None,
    user: Any = None,
    message_key: str = "",
    detail: str = "",
    mailbox: Any = None,
) -> MailLogEntry | None:
    """Note one mail in the log (EML-039), with the mailbox it went through (EML-041); never raises.

    The entry is written in a savepoint of its own, so that a failure here
    leaves a surrounding transaction intact.

    Returns:
        The entry, or ``None`` if it could not be written.
    """
    try:
        with transaction.atomic():
            return MailLogEntry.objects.create(
                direction=direction,
                kind=kind,
                result=result,
                sender=str(sender or "")[:300],
                recipients=_joined(recipients),
                subject=" ".join(str(subject or "").split())[:500],
                project=project if getattr(project, "pk", None) else None,
                mail=mail if getattr(mail, "pk", None) else None,
                user=user if getattr(user, "pk", None) else None,
                message_key=message_key[:64],
                detail=str(detail or "")[:2000],
                mailbox=mailbox if getattr(mailbox, "pk", None) else None,
            )
    except Exception:
        logger.exception("A mail could not be noted in the mail log.")
        return None


def record_incoming(
    *, result: str, sender: str, recipients: str, subject: str, message_key: str, **extra: Any
) -> MailLogEntry | None:
    """Note a mail the fetch looked at (EML-039).

    A mail is noted once per result: when the server renumbers its inbox, the
    fetch looks at every mail again, and a mail that cannot be read is tried
    at every fetch until it works.
    """
    if (
        message_key
        and MailLogEntry.objects.filter(direction=Direction.INCOMING, message_key=message_key, result=result).exists()
    ):
        return None
    return record(
        direction=Direction.INCOMING,
        kind=LogKind.PROJECT,
        result=result,
        sender=sender,
        recipients=recipients,
        subject=subject,
        message_key=message_key,
        **extra,
    )


def retention_days() -> int:
    """How many days entries are kept: as long as the mails, or one year if mails are kept (EML-039)."""
    return MailSettings.load().retention_days or DEFAULT_RETENTION_DAYS


def delete_old_entries(now: datetime.datetime | None = None) -> int:
    """Remove entries past their retention (EML-039, NFA-011); run by the daily maintenance."""
    limit = (now or timezone.now()) - datetime.timedelta(days=retention_days())
    deleted, _per_model = MailLogEntry.objects.filter(timestamp__lt=limit).delete()
    return deleted


def delete_entries_of_addresses(addresses: Iterable[str]) -> int:
    """Remove the entries from or to some addresses – those of an anonymised customer (EML-031, EML-039).

    L1: an entry goes if one of its addresses *is* one of these, not if it merely contains the text.
    """
    from rentalars.mail.suppliers import addresses_of

    wanted = {address.strip().lower() for address in addresses if address and address.strip()}
    if not wanted:
        return 0
    query = Q()
    for address in wanted:
        query |= Q(sender__icontains=address) | Q(recipients__icontains=address)
    ids = [
        entry.pk
        for entry in MailLogEntry.objects.filter(query).only("pk", "sender", "recipients")
        if wanted & addresses_of(entry.sender, entry.recipients)
    ]
    if not ids:
        return 0
    deleted, _per_model = MailLogEntry.objects.filter(pk__in=ids).delete()
    return deleted


def filtered_entries(
    *,
    since: datetime.date | datetime.datetime | None = None,
    until: datetime.date | datetime.datetime | None = None,
    direction: str = "",
    kind: str = "",
    result: str = "",
    text: str = "",
) -> QuerySet[MailLogEntry]:
    """The entries that match the filters of the page and of the API (EML-039).

    Args:
        since: From this day (a date) or moment (a time) on.
        until: Up to and including this day, or up to this moment.
        direction: ``in`` or ``out``.
        kind: ``project`` or ``system``.
        result: One of :class:`~rentalars.mail.models.LogResult`.
        text: Found in sender, recipients, subject, detail, project number or the name of the mailbox.
    """
    from rentalars.core.listing import end_of_day, start_of_day

    entries = MailLogEntry.objects.select_related("project", "user", "mailbox")
    if isinstance(since, datetime.datetime):
        entries = entries.filter(timestamp__gte=since)
    elif isinstance(since, datetime.date):
        entries = entries.filter(timestamp__gte=start_of_day(since))
    if isinstance(until, datetime.datetime):
        entries = entries.filter(timestamp__lt=until)
    elif isinstance(until, datetime.date):
        entries = entries.filter(timestamp__lt=end_of_day(until))
    if direction in Direction.values:
        entries = entries.filter(direction=direction)
    if kind in LogKind.values:
        entries = entries.filter(kind=kind)
    if result in LogResult.values:
        entries = entries.filter(result=result)
    text = text.strip()
    if text:
        entries = entries.filter(
            Q(sender__icontains=text)
            | Q(recipients__icontains=text)
            | Q(subject__icontains=text)
            | Q(detail__icontains=text)
            | Q(project__number__icontains=text)
            | Q(project__former_number__icontains=text)  # ADM-012, ADM-014
            | Q(mailbox_name__icontains=text)  # EML-046: also a deleted mailbox
        )
    return entries
