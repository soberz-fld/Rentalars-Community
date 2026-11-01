# SPDX-License-Identifier: GPL-3.0-or-later
"""An inquiry under Projekte → Anfragen becomes a project (PRJ-107) – and inquiries noted by hand (EML-053).

Besides "Als Servicefall anlegen" (PRJ-090, ``projects.service_cases``) an
inquiry without project tag can become a project: the project form opens
with the subject as name and the customer and contact guessed from the
sender's address – as far as the service case does it –, and saving takes
the mail out of its inbox into the new project. Both or neither: if the
mail cannot be fetched, no project is created.

Opening the form from an inquiry needs write access to the module "E-mail",
as taking a mail over by hand does (EML-042).

EML-053: inquiries can also be created by hand, for example when a call comes in, so that it can be noted at
once for processing in the office.

* An inquiry noted by hand (:func:`create_manual`) is an ``UnknownTagMail``
  with ``source`` "manual": when it came in (never in the future), who called
  – name, phone, e-mail address –, the customer if known, a subject and a
  note. It needs someone to get back to and something it is about.
* It is listed with the others (badge „Notiert“), can be changed and deleted
  by who noted it or who may write in the module "E-mail"
  (:func:`may_change`), and taken off the list like the others.
* "Als Projekt" and "Als Servicefall" suggest its customer, the caller and
  the subject (:func:`manual_suggestions`); taken over – into a new project or
  case, or into an existing project – it becomes a note in the correspondence
  with its time, subject and text, the caller, phone and e-mail address
  (:func:`take_manual_into`). Nothing is fetched; it never starts the
  automations of incoming mails.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, request_rights
from rentalars.mail.models import InquirySource, UnknownTagMail

#: What the project form takes from the suggestions of a service case; "reported by" has no field in a project.
PROJECT_FIELDS = ("name", "customer", "contact")

#: EML-053: the longest note of an inquiry noted by hand – with the caller's data it must fit into a note (EML-051).
MAX_NOTE = 9_000
#: The longest subject – that of a note in the correspondence.
MAX_SUBJECT = 200
#: A clock a little ahead does not refuse "now".
FUTURE_TOLERANCE = datetime.timedelta(minutes=5)
#: The fields of an inquiry noted by hand that can be given and changed.
MANUAL_FIELDS = ("date", "contact_name", "contact_email", "phone", "customer", "subject", "note")


def inquiry_of(request: HttpRequest) -> UnknownTagMail | None:
    """The waiting inquiry named by ``?inquiry=`` (or the form field ``inquiry``), else ``None``.

    Raises:
        Http404: It is not a waiting inquiry, or the user may not take mails over.
    """
    value = request.GET.get("inquiry", "") or request.POST.get("inquiry", "")
    if not value:
        return None
    if not value.isdigit() or not request_rights(request).can_write(Module.EMAIL):
        raise Http404
    # MAT-057: a defect report becomes a service case, not a project.
    return get_object_or_404(UnknownTagMail, pk=int(value), resolved_at__isnull=True, tag="", defect_report=None)


def project_initial(unknown: UnknownTagMail) -> dict[str, Any]:
    """The start values of a new project from an inquiry: the subject without "AW:", customer and contact."""
    from rentalars.projects.service_cases import suggestions_from_inquiry

    suggested = suggestions_from_inquiry(unknown)
    return {name: suggested[name] for name in PROJECT_FIELDS if suggested.get(name) is not None}


def take_into(unknown: UnknownTagMail, project: Any, *, opener: Any = None) -> Any:
    """Take the mail of an inquiry into the project just created (EML-042).

    EML-053: an inquiry noted by hand becomes a note in the correspondence instead.

    Raises:
        MailboxError: The mail is no longer in the inbox, or the mailbox cannot be reached.
    """
    from rentalars.mail.fetching import assign_unknown

    return assign_unknown(unknown, project, opener=opener)


# --- EML-053: inquiries noted by hand -------------------------------------------------------------


def sender_text(*, name: str, email: str, phone: str) -> str:
    """Who the inquiry is from, as the column "Sender" and the API field ``sender`` show it."""
    from rentalars.mail.parsing import format_address

    if email:
        return format_address(name, email)[:300]
    return (name or phone)[:300]


def reporter_text(inquiry: UnknownTagMail) -> str:
    """Name, e-mail address and phone of the caller in one line, e.g. for "reported by" of a service case."""
    from rentalars.mail.parsing import format_address

    who = format_address(inquiry.contact_name, inquiry.contact_email) if inquiry.contact_email else inquiry.contact_name
    return ", ".join(part for part in (who, inquiry.phone) if part)


def _normalised(values: dict[str, Any]) -> dict[str, Any]:
    result = dict(values)
    for name in ("contact_name", "contact_email", "phone", "subject"):
        if name in result:
            result[name] = " ".join(str(result[name] or "").split())
    if "note" in result:
        result["note"] = str(result["note"] or "").strip()
    return result


def _check(inquiry: UnknownTagMail) -> None:
    """What an inquiry noted by hand needs (EML-053).

    Raises:
        ValidationError: Nobody to get back to, nothing it is about, too long, or a time in the future.
    """
    errors: dict[str, str] = {}
    if not (inquiry.contact_name or inquiry.phone or inquiry.contact_email or inquiry.customer_id):
        errors["contact_name"] = _(
            "Say who the inquiry is from: a name, a phone number, an e-mail address or a customer."
        )
    if not (inquiry.subject or inquiry.note):
        errors["note"] = _("Write what the inquiry is about: a subject or a note.")
    elif len(inquiry.note) > MAX_NOTE:
        errors["note"] = _("A note may have at most %(count)d characters.") % {"count": MAX_NOTE}
    if len(inquiry.subject) > MAX_SUBJECT:
        errors["subject"] = _("The subject may have at most %(count)d characters.") % {"count": MAX_SUBJECT}
    if len(inquiry.contact_name) > 200:
        errors["contact_name"] = _("The name may have at most %(count)d characters.") % {"count": 200}
    if len(inquiry.phone) > 60:
        errors["phone"] = _("The phone number may have at most %(count)d characters.") % {"count": 60}
    if inquiry.contact_email:
        from django.core.validators import validate_email

        try:
            validate_email(inquiry.contact_email)
        except ValidationError:
            errors["contact_email"] = _("Enter a valid e-mail address.")
    if inquiry.date is not None and inquiry.date > timezone.now() + FUTURE_TOLERANCE:
        errors["date"] = _("An inquiry has come in already – choose a time that has passed.")
    if errors:
        raise ValidationError(errors)


def _apply(inquiry: UnknownTagMail, values: dict[str, Any]) -> None:
    for name, value in _normalised(values).items():
        if name not in MANUAL_FIELDS:
            raise ValueError(f"Unknown field of an inquiry: {name}")
        if name == "date":
            value = value or timezone.now()
        setattr(inquiry, name, value)
    inquiry.sender = sender_text(name=inquiry.contact_name, email=inquiry.contact_email, phone=inquiry.phone)


@transaction.atomic
def create_manual(*, user: Any, **values: Any) -> UnknownTagMail:
    """Note an inquiry by hand – e.g. a phone call – under Projekte → Anfragen (EML-053).

    Args:
        user: Who notes it.
        **values: ``date`` (now if left out), ``contact_name``, ``contact_email``, ``phone``, ``customer``,
            ``subject``, ``note``.

    Raises:
        ValidationError: Nobody to get back to, nothing it is about, too long, or a time in the future.
    """
    from rentalars.core.audit import record_event

    inquiry = UnknownTagMail(
        source=InquirySource.MANUAL,
        message_key=f"manual:{uuid.uuid4().hex}",
        message_id="",
        created_by=user if getattr(user, "pk", None) else None,
    )
    _apply(inquiry, {"date": None, **values})
    _check(inquiry)
    inquiry.save()
    record_event(inquiry, "inquiry.noted", {"subject": inquiry.subject[:120], "date": inquiry.date.isoformat()})
    return inquiry


def ensure_manual(inquiry: UnknownTagMail) -> None:
    """Refuse an entry that was not noted by hand.

    Raises:
        ValidationError: It is a mail or a defect report.
    """
    if not inquiry.is_manual:
        raise ValidationError(_("Only an inquiry noted by hand can be changed or deleted."))


@transaction.atomic
def update_manual(inquiry: UnknownTagMail, **changes: Any) -> UnknownTagMail:
    """Change an inquiry noted by hand; what is left out stays (EML-053).

    Raises:
        ValidationError: Not noted by hand, dealt with already, or a value is missing or invalid.
    """
    from rentalars.core.audit import record_event

    ensure_manual(inquiry)
    if inquiry.resolved_at is not None:
        raise ValidationError(_("The inquiry was dealt with already."))
    _apply(inquiry, changes)
    _check(inquiry)
    inquiry.version += 1
    inquiry.save()
    record_event(inquiry, "inquiry.changed", {"subject": inquiry.subject[:120]})
    return inquiry


@transaction.atomic
def delete_manual(inquiry: UnknownTagMail) -> None:
    """Delete an inquiry noted by hand (EML-053).

    Raises:
        ValidationError: It is a mail or a defect report.
    """
    from rentalars.core.audit import record_event

    ensure_manual(inquiry)
    record_event(inquiry, "inquiry.deleted", {"subject": inquiry.subject[:120]})
    inquiry.delete()


def may_change(inquiry: UnknownTagMail, user: Any, rights: Any) -> bool:
    """Who may change or delete an inquiry noted by hand: who noted it, or who may write in "E-mail" (EML-053)."""
    if not inquiry.is_manual:
        return False
    if rights.can_write(Module.EMAIL):
        return True
    return inquiry.created_by_id is not None and inquiry.created_by_id == getattr(user, "pk", None)


def manual_suggestions(inquiry: UnknownTagMail) -> dict[str, Any]:
    """What an inquiry noted by hand suggests for a new project or case (EML-053).

    The subject (else the beginning of the note) as name; the customer noted,
    else the one the e-mail address belongs to; the contact with that
    address; without a contact the caller as "reported by".
    """
    from rentalars.customers.models import Contact, Customer

    first_line = next((line.strip() for line in inquiry.note.splitlines() if line.strip()), "")
    name = (inquiry.subject or first_line)[:200] or _("Inquiry noted by hand")
    initial: dict[str, Any] = {"name": name}
    customer = inquiry.customer
    contact = None
    if inquiry.contact_email:
        contacts = Contact.objects.filter(email__iexact=inquiry.contact_email).select_related("customer")
        if customer is not None:
            contacts = contacts.filter(customer=customer)
        contact = contacts.order_by("pk").first()
        if customer is None and contact is None:
            customer = Customer.objects.filter(email__iexact=inquiry.contact_email).order_by("pk").first()
    if contact is not None:
        initial["contact"] = contact
        customer = customer or contact.customer
    if customer is not None:
        initial["customer"] = customer
    if contact is None and reporter_text(inquiry):
        initial["case_contact"] = reporter_text(inquiry)[:250]
    return initial


def note_text(inquiry: UnknownTagMail) -> str:
    """The text of the note an inquiry noted by hand becomes: the caller, phone, e-mail, customer and the note."""
    lines = []
    if inquiry.contact_name:
        lines.append(_("Who: %(name)s") % {"name": inquiry.contact_name})
    if inquiry.phone:
        lines.append(_("Phone: %(phone)s") % {"phone": inquiry.phone})
    if inquiry.contact_email:
        lines.append(_("E-mail: %(address)s") % {"address": inquiry.contact_email})
    if inquiry.customer_id is not None:
        lines.append(_("Customer: %(customer)s") % {"customer": inquiry.customer.name})
    if inquiry.note:
        lines += ["", inquiry.note] if lines else [inquiry.note]
    return "\n".join(lines).strip()


@transaction.atomic
def take_manual_into(inquiry: UnknownTagMail, project: Any) -> Any:
    """Make an inquiry noted by hand a note in the correspondence of a project and take it off the list (EML-053).

    The note stands at the time the inquiry came in, with its subject; its
    writer is who noted the inquiry. Nothing is fetched or sent.

    Returns:
        The note (a ``ProjectMail`` with ``direction`` "note").

    Raises:
        ValidationError: Not noted by hand, or dealt with already.
    """
    from rentalars.mail.notes import add_note

    ensure_manual(inquiry)
    waiting = UnknownTagMail.objects.select_for_update().filter(pk=inquiry.pk, resolved_at__isnull=True).first()
    if waiting is None:
        raise ValidationError(_("The inquiry was dealt with already."))
    note = add_note(
        project,
        text=note_text(inquiry),
        user=inquiry.created_by,
        date=inquiry.date or inquiry.first_seen_at,
        subject=inquiry.subject[:MAX_SUBJECT],
    )
    inquiry.resolved_at = timezone.now()
    inquiry.save(update_fields=["resolved_at"])
    return note
