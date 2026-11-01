# SPDX-License-Identifier: GPL-3.0-or-later
"""Choosing the sender of a mail written in a project (EML-052, closes EML-003).

The requirement: the sender can be chosen, but always according to permissions. One mailbox is free for everybody who
may write e-mails; further sender addresses require permissions.

The addresses a project mail can go out with (:class:`Sender`):

* the address of every active mailbox of the correspondence that can send –
  through its own SMTP server;
* every further address (alias) of such a mailbox – through the SMTP server of
  its mailbox, or of the mailbox that sends the correspondence when its own
  cannot send, with the alias as ``From`` (as service cases do);
* the address a project uses by default (``default_sender``): the mailbox that
  sends the correspondence, for a service case the address for service cases
  (EML-047).

Only mailboxes of the correspondence are offered: an answer to the chosen
address must come back into Rentalars.

Who may use which (:func:`allowed_senders`): everybody who may write
correspondence uses the mailbox that sends the correspondence and the address
the project uses by default; every other address needs one of the roles chosen
for it under Einstellungen → Postfächer (``sender_roles`` of the mailbox or of
the alias). Superusers may use every address. The callers check the right to
write correspondence (``mail.services``).

The default when writing is the project's default address; when answering a
mail that came in through an address the writer may use, that address
(:func:`default_choice`). Automations keep their own sender logic
(``automations.engine``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from email.utils import getaddresses
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from rentalars.mail.models import Direction, Mailbox, MailboxAddress


@dataclass(frozen=True)
class Sender:
    """An address a mail of a project can go out with (EML-052).

    Attributes:
        address: The ``From`` address.
        mailbox: The mailbox whose SMTP server sends the mail.
        owner: The mailbox the address belongs to – the mailbox itself, or the mailbox of the alias. Its
            signature is used (EML-026).
        alias: The further address of the mailbox, if the address is one.
        holders: The mailbox and aliases whose ``sender_roles`` decide who may use the address – more than one
            when the same address is listed twice.
    """

    address: str
    mailbox: Mailbox
    owner: Mailbox
    alias: MailboxAddress | None = None
    holders: tuple[Any, ...] = ()

    @property
    def key(self) -> str:
        """The address in lower case, for comparing."""
        return (self.address or "").strip().lower()

    @property
    def name(self) -> str:
        """The name shown with the address: that of the mailbox it belongs to."""
        return self.owner.name

    @property
    def label(self) -> str:
        """Name and address, as the choice shows them."""
        return f"{self.name} <{self.address}>" if self.name else self.address


def _key(address: str) -> str:
    return (address or "").strip().lower()


def _sending_mailbox(owner: Mailbox, outgoing: Mailbox | None) -> Mailbox | None:
    """The mailbox whose SMTP server sends for an address of ``owner``: its own, else the outgoing one."""
    if owner.can_send:
        return owner
    if outgoing is not None and outgoing.can_send:
        return outgoing
    return None


def default_sender(project: Any) -> Sender | None:
    """The address a mail of the project goes out with unless another is chosen (EML-041, EML-047).

    A mail written in a service case goes out with the address of the role
    "only for service cases" – through the mailbox of that address when it
    can send, else through the outgoing mailbox. Every other mail goes out
    through the outgoing mailbox with its address. ``None`` without an
    outgoing mailbox; the outgoing mailbox is returned even when it cannot
    send, so that sending says what is missing.
    """
    from rentalars.mail.aliases import service_case_address
    from rentalars.mail.mailboxes import outgoing_mailbox

    outgoing = outgoing_mailbox()
    if getattr(project, "is_service_case", False):
        alias = service_case_address()
        if alias is not None:
            mailbox = _sending_mailbox(alias.mailbox, outgoing)
            if mailbox is not None:
                return Sender(alias.address, mailbox, alias.mailbox, alias, (alias,))
    if outgoing is None:
        return None
    return Sender(outgoing.address, outgoing, outgoing, None, (outgoing,))


def candidates(project: Any = None) -> list[Sender]:
    """Every address a mail of the project can go out with: the default first, then the outgoing mailbox.

    The others follow by the name of their mailbox; an address listed twice
    appears once.
    """
    from rentalars.mail.mailboxes import outgoing_mailbox

    found: dict[str, Sender] = {}

    def add(sender: Sender | None) -> None:
        if sender is None or not sender.key:
            return
        existing = found.get(sender.key)
        if existing is None:
            found[sender.key] = sender
        else:
            found[sender.key] = replace(existing, holders=existing.holders + sender.holders)

    outgoing = outgoing_mailbox()
    if project is not None:
        add(default_sender(project))
    if outgoing is not None and outgoing.can_send:
        add(Sender(outgoing.address, outgoing, outgoing, None, (outgoing,)))
    boxes = (
        Mailbox.objects.filter(is_active=True, for_correspondence=True)
        .prefetch_related("sender_roles", "aliases__sender_roles")
        .order_by("name", "pk")
    )
    for box in boxes:
        if box.can_send:
            add(Sender(box.address, box, box, None, (box,)))
        mailbox = _sending_mailbox(box, outgoing)
        if mailbox is None:
            continue
        for alias in box.aliases.all():
            add(Sender(alias.address, mailbox, box, alias, (alias,)))
    return list(found.values())


def _free_keys(project: Any) -> set[str]:
    """The addresses everybody who may write correspondence uses: the outgoing mailbox and the project's default."""
    from rentalars.mail.mailboxes import outgoing_mailbox

    keys = set()
    outgoing = outgoing_mailbox()
    if outgoing is not None:
        keys.add(_key(outgoing.address))
    default = default_sender(project) if project is not None else None
    if default is not None:
        keys.add(default.key)
    keys.discard("")
    return keys


def _role_ids(user: Any) -> set[int]:
    if not getattr(user, "pk", None):
        return set()
    return set(user.roles.values_list("pk", flat=True))


def may_use(sender: Sender, user: Any, *, free: set[str], roles: set[int] | None = None) -> bool:
    """Whether a user may send from an address (EML-052).

    Args:
        sender: The address.
        user: Who writes.
        free: The addresses open to everybody who may write correspondence (:func:`_free_keys`).
        roles: The IDs of the user's roles, if looked up already.
    """
    if getattr(user, "is_superuser", False) or sender.key in free:
        return True
    roles = _role_ids(user) if roles is None else roles
    if not roles:
        return False
    return any(role.pk in roles for holder in sender.holders for role in holder.sender_roles.all())


def allowed_senders(project: Any, user: Any) -> list[Sender]:
    """The addresses a user may send a mail of the project from, the default first (EML-052).

    The right to write correspondence is checked by the caller.
    """
    options = candidates(project)
    if not options:
        return []
    free = _free_keys(project)
    roles = None if getattr(user, "is_superuser", False) else _role_ids(user)
    return [sender for sender in options if may_use(sender, user, free=free, roles=roles)]


def pick(options: list[Sender], address: str) -> Sender | None:
    """The option with this address, or ``None``."""
    key = _key(address)
    return next((sender for sender in options if sender.key == key), None) if key else None


def answer_sender(options: list[Sender], answer_to: Any) -> Sender | None:
    """The address a mail being answered came in through, if it is among ``options`` (EML-052).

    A received mail came in through an address in its ``To`` or ``Cc`` – else
    through the address of the mailbox it was fetched from. An answer to a
    sent mail goes out from the address that mail was sent from.
    """
    if answer_to is None or not options:
        return None
    by_key = {sender.key: sender for sender in options}
    if answer_to.direction == Direction.OUTGOING:
        return by_key.get(_key(answer_to.sender_address))
    if answer_to.direction != Direction.INCOMING:
        return None
    for _name, address in getaddresses([answer_to.to_addresses or "", answer_to.cc_addresses or ""]):
        if _key(address) in by_key:
            return by_key[_key(address)]
    if answer_to.mailbox_id is not None and answer_to.mailbox is not None:
        return by_key.get(_key(answer_to.mailbox.address))
    return None


def default_choice(options: list[Sender], answer_to: Any = None) -> Sender | None:
    """The address chosen at first: the one an answered mail came in through, else the project's default."""
    return answer_sender(options, answer_to) or (options[0] if options else None)


def chosen_sender(project: Any, user: Any, address: str = "", *, answer_to: Any = None) -> Sender | None:
    """The sender of a mail written by ``user``: the address asked for, else the default (EML-052).

    Returns:
        The sender; ``None`` when nothing can send (sending then says what is missing).

    Raises:
        PermissionDenied: The user may not send from the address asked for.
        ValidationError: The address is none Rentalars can send from (field ``sender``).
    """
    options = allowed_senders(project, user)
    if not _key(address):
        return default_choice(options, answer_to)
    found = pick(options, address)
    if found is not None:
        return found
    if pick(candidates(project), address) is not None:
        raise PermissionDenied(_("You may not send from %(address)s.") % {"address": address.strip()})
    raise ValidationError(
        {"sender": _("%(address)s is no address Rentalars can send from.") % {"address": address.strip()}}
    )
