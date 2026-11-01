# SPDX-License-Identifier: GPL-3.0-or-later
"""Who may see which mail, and what can be done with mails (EML-015, EML-022, EML-029, EML-031).

Rights (EML-029, AUT-019):

* A mail of a project is seen by whoever may **read** the project (not only
  its deployment view) **and** has the special right "read correspondence".
* Writing and sending need "write and send correspondence" in addition.
* EML-055: a message "with lock" needs the price right in addition; an
  open one is read by the crew of the project as well (``mail.locks``).
* The list of unknown tags and inquiries (under Projects, EML-042) and the
  mailboxes belong to the module "E-mail" (AUT-014): reading the list needs
  read access, assigning from it and changing the mailboxes need write
  access, deleting a mailbox delete access (EML-041).
* The signature belongs to the company: changing it needs write access to
  the administration; everybody who may write mails sees it (EML-034).
* The mail log needs read access to the administration (EML-039).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, Rights, SpecialRight
from rentalars.core.audit import record_event
from rentalars.mail.models import MailAttachment, MailSettings, ProjectMail
from rentalars.projects.models import Project


def may_read_mail(rights: Rights) -> bool:
    """The special right to read correspondence (AUT-019)."""
    return rights.has(SpecialRight.CORRESPONDENCE_READ)


def may_write_mail(rights: Rights) -> bool:
    """Both correspondence rights: sending implies reading what one answers."""
    return rights.has(SpecialRight.CORRESPONDENCE_READ) and rights.has(SpecialRight.CORRESPONDENCE_WRITE)


def may_read_all_mail(rights: Rights) -> bool:
    """EML-055: the correspondence right and the price right – every message, also those with lock."""
    return may_read_mail(rights) and rights.has(SpecialRight.PRICES)


def may_edit_signature(rights: Rights) -> bool:
    """Changing the signature of everybody needs write access to the administration (EML-034)."""
    return rights.can_write(Module.ADMINISTRATION)


def may_see_signature(rights: Rights) -> bool:
    """Who writes mails, sets up the mailbox or reads the administration sees the signature (EML-034)."""
    return may_write_mail(rights) or rights.can_write(Module.EMAIL) or rights.can_read(Module.ADMINISTRATION)


def may_open_mail_settings(rights: Rights) -> bool:
    """The page with mailbox and signature: for who may change one of them (EML-034, EML-035)."""
    return rights.can_write(Module.EMAIL) or may_edit_signature(rights)


def visible_mails(rights: Rights, user: Any) -> QuerySet[ProjectMail]:
    """All mails a user may see: of readable projects, with the correspondence right (EML-029).

    EML-055: those with lock only with the price right as well.
    """
    from rentalars.projects.access import readable_projects

    if not may_read_mail(rights):
        return ProjectMail.objects.none()
    mails = ProjectMail.objects.filter(project__in=readable_projects(rights, user).values("pk"))
    return mails if rights.has(SpecialRight.PRICES) else mails.filter(locked=False)


def search_mails(rights: Rights, user: Any, text: str, *, limit: int = 20) -> list[ProjectMail]:
    """Mails found by subject, sender or text (EML-022), within the rights of the user."""
    text = text.strip()
    if len(text) < 2:
        return []
    return list(
        visible_mails(rights, user)
        .filter(
            Q(subject__icontains=text)
            | Q(sender_address__icontains=text)
            | Q(sender_name__icontains=text)
            | Q(text_body__icontains=text)
        )
        .select_related("project")
        .order_by("-date")[:limit]
    )


@transaction.atomic
def reassign(mail: ProjectMail, project: Project, *, user: Any) -> ProjectMail:
    """Move a mail to another project (EML-015); the change log records it."""
    if mail.project_id == project.pk:
        return mail
    old = mail.project
    mail.project = project
    mail.save()
    # EML-055: with the mail's ID – the history shows the subject only to who may read it (mail.history).
    details = {"subject": mail.subject, "from": old.number, "to": project.number, "mail": mail.pk}
    record_event(project, "mail.reassigned", details)
    record_event(old, "mail.reassigned", details)
    return mail


def _delete_files(attachments: list[MailAttachment]) -> None:
    stored = [attachment.file for attachment in attachments]
    transaction.on_commit(lambda: [file.delete(save=False) for file in stored])


def delete_mail(mail: ProjectMail) -> None:
    """Remove a mail from Rentalars with its attachments (the mailbox is not touched)."""
    with transaction.atomic():
        attachments = list(mail.attachments.all())
        # EML-055: the history shows the subject of a removed message only to who reads those with lock.
        details = {"subject": mail.subject, "date": mail.date.isoformat(), "mail": mail.pk}
        record_event(mail.project, "mail.deleted", details)
        mail.delete()
        _delete_files(attachments)


def delete_old_mails(now: datetime.datetime | None = None) -> int:
    """Remove mails older than the retention period of the mailbox settings (EML-031, NFA-011).

    Run by the daily maintenance; with a period of 0 nothing is removed.
    Files taken over into a project stay: they belong to the project now.
    """
    days = MailSettings.load().retention_days
    if not days:
        return 0
    limit = (now or timezone.now()) - datetime.timedelta(days=days)
    count = 0
    for mail in ProjectMail.objects.filter(date__lt=limit):
        delete_mail(mail)
        count += 1
    return count


def delete_old_mail_log_entries(now: datetime.datetime | None = None) -> int:
    """Remove mail log entries past their retention (EML-039); run by the daily maintenance."""
    from rentalars.mail.log import delete_old_entries

    return delete_old_entries(now)


def delete_mails_of_customer(customer: Any) -> int:
    """Remove the mails that concern a customer who is anonymised (EML-031, KND-010).

    These are all mails of the customer's projects, and every other mail
    from or to an address of the customer or its contacts.
    """
    addresses = {
        address.lower() for address in [customer.email, *customer.contacts.values_list("email", flat=True)] if address
    }
    mails = ProjectMail.objects.filter(project__customer=customer)
    if addresses:
        # L1: whole addresses, not parts of them – "anna@musik.example" is not in "hanna@musik.example".
        from rentalars.mail.suppliers import addresses_of

        candidates = Q()
        for address in addresses:
            candidates |= (
                Q(sender_address__icontains=address)
                | Q(to_addresses__icontains=address)
                | Q(cc_addresses__icontains=address)
                | Q(bcc_addresses__icontains=address)
            )
        exact_ids = [
            mail.pk
            for mail in ProjectMail.objects.filter(candidates)
            if addresses & addresses_of(mail.sender_address, mail.to_addresses, mail.cc_addresses, mail.bcc_addresses)
        ]
        mails = mails | ProjectMail.objects.filter(pk__in=exact_ids)
    count = 0
    for mail in mails.distinct():
        delete_mail(mail)
        count += 1
    # The mail log names the same addresses (EML-039).
    from rentalars.mail.log import delete_entries_of_addresses

    delete_entries_of_addresses(addresses)
    # EML-053: inquiries noted by hand for the customer or with one of its addresses.
    from rentalars.mail.models import InquirySource, UnknownTagMail

    noted = Q(customer=customer)
    for address in addresses:
        noted |= Q(contact_email__iexact=address)
    UnknownTagMail.objects.filter(noted, source=InquirySource.MANUAL).delete()
    return count


def save_settings(mail_settings: MailSettings) -> MailSettings:
    """Store what holds for all mailboxes: interval, size limit, retention, sender name (EML-005, EML-031).

    The mailboxes themselves are stored by ``mail.mailboxes.save_mailbox`` (EML-041).
    """
    mail_settings.full_clean()
    mail_settings.save()
    return mail_settings


def require_mail_read(rights: Rights) -> None:
    """Refuse without the right to read correspondence."""
    if not may_read_mail(rights):
        raise PermissionDenied(_("You do not have the right to read correspondence."))


def require_mail_write(rights: Rights) -> None:
    """Refuse without the right to write correspondence."""
    if not may_write_mail(rights):
        raise PermissionDenied(_("You do not have the right to write correspondence."))


def require_mail_read_all(rights: Rights) -> None:
    """EML-055: refuse unless the user reads every message – what reads all of them, e.g. the AI, needs it."""
    require_mail_read(rights)
    if not rights.has(SpecialRight.PRICES):
        raise PermissionDenied(
            _("This reads messages with lock as well – that needs the right “See prices and calculation”.")
        )
