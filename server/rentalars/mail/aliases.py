# SPDX-License-Identifier: GPL-3.0-or-later
"""Further addresses of a mailbox – aliases such as ``support@`` and ``projekt@`` (EML-047).

A mailbox often receives the mails of several addresses. Each address can
be listed with the mailbox (:class:`~rentalars.mail.models.MailboxAddress`)
and then has its own rule for mails **without** project tag:

* "do not take in" – the mail stays in the inbox, untouched (EML-013);
* "as an inquiry" – it waits under Projekte → Anfragen (EML-041, EML-042),
  and automations of the trigger "mail without project tag" run (ADM-013);
* "create a service case at once" – a service case (PRJ-090) is made of it
  with the mail in it; the automations run as for an inquiry.

Mails with a project tag and replies to assigned mails go to their project
whatever address they came to.

Which address a mail went to is read from ``Delivered-To``,
``X-Original-To``, ``To`` and ``Cc``, in this order (:func:`alias_for`). The
first listed address found there decides. The mailbox's own address is
looked at last: many servers write it into ``Delivered-To`` even for a mail
to an alias. A mail to no listed address follows the mailbox's own address –
its entry in the list if it is listed, else ``Mailbox.process_untagged``.

EML-049: mails without tag are taken in only from a point in time
(``untagged_since`` of the mailbox or of the listed address that decides) and,
if so set, only while still unread (``untagged_unread_only``). The point is
set to the moment the handling is switched on (:func:`stamp_untagged_since`)
and can be changed. Which moment a mail counts by is when it arrived in the
mailbox (IMAP ``INTERNALDATE``), else its ``Date`` header; a mail with
neither stays untouched (:func:`untagged_skip`). Mails with a tag, replies
and answers to deployment requests are not affected.

The role "only for service cases" (``for_service_cases``, at most one
address): mails written in a service case go out with this address as
sender (:func:`sender_for`); without it they go out with the address of the
outgoing mailbox, as all project mails.

EML-052: who may choose an address as sender is set per address
(``sender_roles``); see ``mail.senders``.
"""

from __future__ import annotations

import datetime
from email.utils import getaddresses
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.mail.models import Mailbox, MailboxAddress, Untagged


def _addresses(text: str) -> list[str]:
    """The addresses in a header value, in lower case and in their order."""
    return [address.strip().lower() for _name, address in getaddresses([text or ""]) if address.strip()]


def recipient_addresses(headers: Any) -> list[str]:
    """The addresses a mail went to: ``Delivered-To``, ``X-Original-To``, ``To``, ``Cc`` – in this order."""
    return list(dict.fromkeys(_addresses(headers.delivered) + _addresses(headers.to)))


def alias_for(mailbox: Mailbox, headers: Any, aliases: list[MailboxAddress] | None = None) -> MailboxAddress | None:
    """The listed address of the mailbox a mail went to, or ``None`` if none is listed for it (EML-047).

    Args:
        mailbox: The mailbox the mail was fetched from.
        headers: The headers of the mail (``mail.parsing.Headers``).
        aliases: The addresses of the mailbox, if loaded already.
    """
    listed = {alias.address.lower(): alias for alias in (aliases if aliases is not None else mailbox.aliases.all())}
    if not listed:
        return None
    own = (mailbox.address or "").strip().lower()
    for address in recipient_addresses(headers):
        if address != own and address in listed:
            return listed[address]
    return listed.get(own)


def untagged_rule(mailbox: Mailbox, headers: Any) -> tuple[str, MailboxAddress | None]:
    """What becomes of a mail without project tag: ``(Untagged value, listed address or None)`` (EML-047)."""
    alias = alias_for(mailbox, headers)
    if alias is not None:
        return alias.untagged, alias
    return (Untagged.INQUIRY if mailbox.process_untagged else Untagged.IGNORE), None


def untagged_skip(holder: Mailbox | MailboxAddress, *, received: datetime.datetime | None, seen: bool) -> str:
    """Why a mail without tag is left in the inbox although ``holder`` takes such mails in (EML-049).

    Args:
        holder: The listed address that decides, else the mailbox.
        received: When the mail arrived in the mailbox (``INTERNALDATE``), else its ``Date`` header.
        seen: Whether the mail is marked as read in the mailbox.

    Returns:
        ``"before_cutoff"``, ``"read"`` (keys of ``mail.models.LEFT_REASONS``) – or ``""``: take it in.
    """
    since = holder.untagged_since
    if since is not None and (received is None or received < since):
        return "before_cutoff"
    if holder.untagged_unread_only and seen:
        return "read"
    return ""


def stamp_untagged_since(record: Mailbox | MailboxAddress, *, now: datetime.datetime | None = None) -> None:
    """Keep ``untagged_since`` in step with the switch "take in mails without tag" (EML-049).

    While mails without tag are taken in, the point in time is set – to now
    if it is empty, e.g. when the switch is just turned on and nobody gave a
    moment; a moment given stays. Switched off, it is emptied, so that
    switching on again starts from that moment.
    """
    if isinstance(record, MailboxAddress):
        taking = record.untagged != Untagged.IGNORE
    else:
        taking = record.process_untagged
    if not taking:
        record.untagged_since = None
    elif record.untagged_since is None:
        record.untagged_since = now or timezone.now()


def takes_untagged(mailbox: Mailbox) -> bool:
    """Whether a mailbox takes in mails without tag at all – by itself or through one of its addresses."""
    if mailbox.process_untagged:
        return True
    return mailbox.aliases.exclude(untagged=Untagged.IGNORE).exists()


def service_case_address() -> MailboxAddress | None:
    """The address with the role "only for service cases" of an active mailbox, if there is one (EML-047)."""
    return (
        MailboxAddress.objects.filter(for_service_cases=True, mailbox__is_active=True)
        .select_related("mailbox")
        .order_by("pk")
        .first()
    )


def sender_for(project: Any) -> tuple[Mailbox | None, str]:
    """The mailbox a mail of a project goes out through, and its sender address (EML-041, EML-047).

    A mail written in a service case goes out with the address of the role
    "only for service cases" – through the mailbox of that address when it
    can send, else through the outgoing mailbox. Every other mail goes out
    through the outgoing mailbox with its address.

    EML-052: the default of ``mail.senders.default_sender``; the
    writer may choose another address there.
    """
    from rentalars.mail.senders import default_sender

    sender = default_sender(project)
    if sender is None:
        return None, ""
    return sender.mailbox, sender.address


@transaction.atomic
def save_address(alias: MailboxAddress) -> list[str]:
    """Store an address of a mailbox; the role "only for service cases" goes from another address to it.

    Returns:
        Notes on another address that gave up the role, for the page.

    Raises:
        ValidationError: The address is invalid or listed for this mailbox already.
    """
    stamp_untagged_since(alias)  # EML-049
    alias.full_clean()
    notes = []
    if alias.for_service_cases:
        others = MailboxAddress.objects.select_for_update().filter(for_service_cases=True).exclude(pk=alias.pk)
        for other in others:
            other.for_service_cases = False
            other.save(update_fields=["for_service_cases"])
            notes.append(_("%(address)s is no longer the address for service cases.") % {"address": other.address})
    alias.save()
    return notes


def delete_address(alias: MailboxAddress) -> None:
    """Remove an address from the list; its mails then follow the mailbox's own rule (EML-047)."""
    alias.delete()
