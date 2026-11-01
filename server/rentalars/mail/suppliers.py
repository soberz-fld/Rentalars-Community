# SPDX-License-Identifier: GPL-3.0-or-later
"""Mails of a project with a supplier of subrentals (PRJ-106).

A mail of a project belongs to the subrentals of a supplier when it was
written with that supplier: from the supplier's e-mail address or to it.
``ProjectMail.supplier`` keeps that link:

* When a mail is stored – fetched (``mail.fetching.import_mail``) or sent
  from Rentalars (``mail.sending.send_project_mail``) – the addresses of
  sender, recipients and copy recipients are compared with the e-mail
  addresses of the suppliers. If exactly one supplier matches, the mail is
  linked to it. A mail written from the page "Zumietung bei …" names its
  supplier itself.
* By hand – on the page of the mail or through the API – the link can be
  set to another supplier or removed.

The page "Zumietung bei …" lists the linked mails of the project and, as
well, the mails from or to the supplier's address that are linked to
nobody yet: the address may have been entered after the mail arrived.
"""

from __future__ import annotations

from email.utils import getaddresses
from typing import Any

from django.db.models import Q, QuerySet

from rentalars.mail.models import ProjectMail
from rentalars.masterdata.models import Supplier


def addresses_of(*texts: str) -> set[str]:
    """The e-mail addresses in header texts such as ``Name <a@b.example>, c@d.example`` – in lower case."""
    return {address.strip().lower() for _name, address in getaddresses([text for text in texts if text]) if address}


def mail_addresses(mail: ProjectMail) -> set[str]:
    """Sender, recipients and copy recipients of a mail (not the blind copies)."""
    return addresses_of(mail.sender_address, mail.to_addresses, mail.cc_addresses)


def supplier_for(addresses: set[str]) -> Supplier | None:
    """The one supplier whose e-mail address is among ``addresses``; ``None`` for none or several."""
    if not addresses:
        return None
    condition = Q()
    for address in addresses:
        condition |= Q(email__iexact=address)
    found = list(Supplier.objects.exclude(email="").filter(condition)[:2])
    return found[0] if len(found) == 1 else None


def set_supplier(mail: ProjectMail, supplier: Supplier | None) -> ProjectMail:
    """Link a mail to a supplier by hand, or remove the link (``None``); the change log records it."""
    if mail.supplier_id == (supplier.pk if supplier is not None else None):
        return mail
    mail.supplier = supplier
    mail.save()
    return mail


def mails_with(project: Any, supplier: Supplier) -> QuerySet[ProjectMail]:
    """The mails of a project with a supplier: linked to it, or from or to its address and linked to nobody.

    Addresses are compared exactly, not as part of a longer address:
    ``max@verleih.example`` is not ``x@verleih.example``.
    """
    linked = Q(supplier=supplier)
    if not supplier.email:
        return ProjectMail.objects.filter(project=project).filter(linked)
    address = supplier.email.strip().lower()
    candidates = Q(supplier__isnull=True) & (
        Q(sender_address__iexact=address) | Q(to_addresses__icontains=address) | Q(cc_addresses__icontains=address)
    )
    unlinked = [
        pk
        for pk, sender, to, cc in ProjectMail.objects.filter(project=project)
        .filter(candidates)
        .values_list("pk", "sender_address", "to_addresses", "cc_addresses")
        if address in addresses_of(sender, to, cc)
    ]
    return ProjectMail.objects.filter(project=project).filter(linked | Q(pk__in=unlinked))


def supplier_from(value: str, answer_to: ProjectMail | None = None) -> Supplier | None:
    """The supplier a new mail is written to: named by the page "Zumietung bei …", or that of the mail answered."""
    if str(value).isdigit():
        return Supplier.objects.filter(pk=int(value)).first()
    if answer_to is not None and answer_to.supplier_id is not None:
        return answer_to.supplier
    return None
