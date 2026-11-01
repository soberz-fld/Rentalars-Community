# SPDX-License-Identifier: GPL-3.0-or-later
"""Writing and answering mails from a project (EML-024, EML-025, EML-011).

A mail sent from a project

* goes out through the SMTP server of the mailbox that sends the
  correspondence, always encrypted (EML-002, EML-041), with that mailbox as
  sender – a mail of a service case with the address for service cases, if
  one is set (EML-047, ``mail.aliases.sender_for``); EML-052: or
  with another address the writer chose and may use (``mail.senders``) –
  through the SMTP server of its mailbox, an alias with itself as ``From``;
* carries the project's tag in the subject, so that the answer comes back
  to the project by itself (EML-011);
* as an answer, refers to the mail it answers (``In-Reply-To``,
  ``References``) – an answer to the answer is assigned even if somebody
  removed the tag (EML-012);
* is stored in the project like a received one, with its attachments;
* names the writer and the company as sender – "Max Mustermann | Firma
  Muster" – with the address of the mailbox (EML-038);
* carries the company's signature with the writer's data, as text and as
  HTML part (EML-034) – the signature of the sender's mailbox, if it has one
  (EML-026);
* can go to further recipients in copy (CC) and in blind copy (BCC), and an
  answer can go to everybody the answered mail went to (EML-037);
* is noted in the mail log, sent or failed, with the mailbox (EML-039,
  EML-041).

Rentalars never sends anything on its own in reply to a received mail
(EML-030) – with one deliberate exception: an automation may
answer a mail without project tag, protected against loops (ADM-013,
``automations.engine``).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rentalars.core.i18n import file_name as download_name
from rentalars.core.i18n import local_pattern
from rentalars.mail import log
from rentalars.mail.locks import default_lock
from rentalars.mail.mailboxes import own_addresses, smtp_session
from rentalars.mail.models import (
    AssignedBy,
    Direction,
    LogKind,
    LogResult,
    MailAttachment,
    Mailbox,
    MailSettings,
    ProjectMail,
    message_key,
)
from rentalars.mail.parsing import format_address
from rentalars.mail.senders import Sender, default_sender
from rentalars.mail.signature import Signature, render_signature, sender_header, sender_name
from rentalars.mail.suppliers import addresses_of, supplier_for
from rentalars.mail.tags import subject_with_tag
from rentalars.masterdata.models import Supplier
from rentalars.projects.models import Project


@dataclass
class OutgoingAttachment:
    """A file to send along."""

    filename: str
    content_type: str
    data: bytes


def split_addresses(text: str) -> list[str]:
    """``"a@x.example, Bea <b@y.example>; c@z.example"`` → the addresses as written, checked.

    Names keep their umlauts; a name with a comma is put in quotes (EML-037).

    Raises:
        ValidationError: An address is not valid.
    """
    addresses = []
    for name, address in getaddresses([text.replace(";", ",")]):
        if not address:
            continue
        validate_email(address)
        addresses.append(format_address(name, address))
    return addresses


def _address_key(entry: str) -> str:
    return (getaddresses([entry])[0][1] or entry).strip().lower()


def reply_recipients(mail: ProjectMail, *, everyone: bool, own_address: str = "") -> tuple[str, str]:
    """``(to, cc)`` of an answer to a mail (EML-024, EML-037).

    An answer goes to the sender of a received mail, or to the recipients of
    a sent one. "Answer all" (``everyone``) adds every other recipient of the
    original – To and CC – except Rentalars' own mailboxes (EML-041).
    """
    seen = own_addresses()
    if own_address.strip():
        seen.add(own_address.strip().lower())

    def unique(entries: list[str]) -> list[str]:
        result = []
        for entry in entries:
            key = _address_key(entry)
            if key and key not in seen:
                seen.add(key)
                result.append(entry)
        return result

    def listed(text: str) -> list[str]:
        return [format_address(name, address) for name, address in getaddresses([text]) if address]

    if mail.direction == Direction.INCOMING:
        to = unique([mail.sender_label] if mail.sender_address else [])
        if everyone:
            to += unique(listed(mail.to_addresses))
    else:
        to = unique(listed(mail.to_addresses))
    cc = unique(listed(mail.cc_addresses)) if everyone else []
    return ", ".join(to), ", ".join(cc)


def body_as_html(body: str) -> str:
    """The text of a mail as HTML, line for line, for the HTML part (EML-034)."""
    lines = [html.escape(line, quote=False) for line in body.splitlines()]
    return "<br>\n".join(lines)


def mail_parts(body: str, signature: Signature) -> tuple[str, str]:
    """The text part and the HTML part of a mail with signature (EML-034).

    Without a signature there is no HTML part: the text alone is the mail,
    as before.
    """
    if not signature:
        return body, ""
    text = f"{body.rstrip()}\n\n-- \n{signature.text}\n"
    document = (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        f'<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px;">{body_as_html(body.rstrip())}</div>'
        f'<br><div class="signature">{signature.html}</div>'
        "</body></html>"
    )
    return text, document


def reply_subject(subject: str) -> str:
    """The subject of an answer: "AW: …" unless it starts with an answer prefix already."""
    stripped = subject.strip()
    if stripped.lower().startswith(("aw:", "re:", "antw:")):
        return stripped
    # UIX-029: "Re:" in English.
    prefix = pgettext("prefix of the subject of an answer", "Re")
    return f"{prefix}: {stripped}"


def quoted(mail: ProjectMail) -> str:
    """The text of a mail, quoted for an answer."""
    when = timezone.localtime(mail.date).strftime(local_pattern("%d.%m.%Y %H:%M"))
    lines = [_("On %(date)s, %(sender)s wrote:") % {"date": when, "sender": mail.sender_label}]
    lines += [f"> {line}" for line in (mail.text_body or "").splitlines()]
    return "\n\n\n" + "\n".join(lines)


def _send(mailbox: Mailbox, message: EmailMessage) -> None:
    """Hand the message to the SMTP server of the mailbox – encrypted, with login if a user is set.

    Raises:
        ValidationError: The server could not be reached or refused the mail.
    """
    with smtp_session(mailbox) as server:
        server.send_message(message)


def _checked(field: str, text: str) -> list[str]:
    try:
        return split_addresses(text)
    except ValidationError as error:
        raise ValidationError({field: _("An address is not valid.")}) from error


def send_project_mail(
    project: Project,
    *,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    attachments: list[OutgoingAttachment] | None = None,
    answer_to: ProjectMail | None = None,
    with_signature: bool = True,
    user: Any,
    supplier: Supplier | None = None,
    sender: Sender | None = None,
    locked: bool | None = None,
) -> ProjectMail:
    """Send a mail from a project through the outgoing mailbox and store it there (EML-024, EML-041).

    Args:
        project: The project the mail belongs to; its tag goes into the subject.
        to: Recipients, separated by commas or semicolons.
        subject: The subject; the tag is added if missing (EML-011).
        body: The text as written.
        cc: Recipients in copy.
        bcc: Recipients in blind copy; the others do not see them (EML-037).
        attachments: Files to send along (EML-025).
        answer_to: The mail this one answers (EML-012).
        with_signature: Add the company's signature (EML-034).
        user: Who writes; names the sender (EML-038) and fills the signature.
        supplier: PRJ-106: the supplier of subrentals the mail is written to, from the page of the
            subrental; without one, the supplier whose address is among the recipients, if any.
        sender: EML-052: the address chosen (``mail.senders.chosen_sender`` checks that the writer
            may use it); the project's default when ``None``.
        locked: EML-055: the mail is stored with lock or open; ``None``: as the mail settings say for
            the project or case (``mail.locks.default_lock``). The caller decided what the writer may.

    Raises:
        ValidationError: The mailbox cannot send, an address is invalid, or
            the server refused the mail.
    """
    # EML-047: a mail of a service case goes out with the address for service cases, if one is set.
    chosen = sender or default_sender(project)
    if chosen is None or not chosen.mailbox.can_send or not chosen.address:
        raise ValidationError(_("Sending is not set up. An administrator fills in the mailbox first."))
    mailbox, sender_address = chosen.mailbox, chosen.address
    fallback_name = MailSettings.load().sender_name
    to_list = _checked("to", to)
    cc_list = _checked("cc", cc)
    bcc_list = _checked("bcc", bcc)
    if not to_list:
        raise ValidationError({"to": _("Enter at least one recipient.")})
    # A line break in the subject (the field is one line, a request need not be) would be refused as a header.
    subject = subject_with_tag(" ".join(subject.split()) or project.name, project.number)
    # EML-026: the signature of the mailbox the address belongs to, else the common one.
    signature = render_signature(user, mailbox=chosen.owner) if with_signature else Signature("", "")
    text, html_document = mail_parts(body, signature)

    message = EmailMessage()
    # EML-038: "Max Mustermann | Firma Muster" <projekte@…>; answers still reach the mailbox.
    message["From"] = sender_header(user, sender_address, fallback_name)
    message["To"] = ", ".join(to_list)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    if bcc_list:
        # smtplib sends to these addresses but never transmits the header itself.
        message["Bcc"] = ", ".join(bcc_list)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    domain = sender_address.rsplit("@", 1)[-1]
    message["Message-ID"] = make_msgid(domain=domain)
    references = ""
    if answer_to is not None:
        message["In-Reply-To"] = answer_to.message_id
        references = f"{answer_to.references} {answer_to.message_id}".strip()
        message["References"] = references
    message.set_content(text)
    if html_document:
        message.add_alternative(html_document, subtype="html")
    for attachment in attachments or []:
        maintype, _slash, subtype = (attachment.content_type or "application/octet-stream").partition("/")
        message.add_attachment(
            attachment.data, maintype=maintype, subtype=subtype or "octet-stream", filename=attachment.filename
        )

    recipients = to_list + cc_list + bcc_list
    try:
        _send(mailbox, message)
    except ValidationError as error:
        log.record(
            direction=Direction.OUTGOING,
            kind=LogKind.PROJECT,
            result=LogResult.FAILED,
            sender=sender_address,
            mailbox=mailbox,
            recipients=recipients,
            subject=subject,
            project=project,
            user=user,
            message_key=message_key(message["Message-ID"]),
            detail=" ".join(error.messages),
        )
        raise

    with transaction.atomic():
        mail = ProjectMail.objects.create(
            project=project,
            direction=Direction.OUTGOING,
            message_key=message_key(message["Message-ID"]),
            message_id=message["Message-ID"],
            in_reply_to=answer_to.message_id if answer_to is not None else "",
            references=references,
            subject=subject[:500],
            sender_name=sender_name(user, fallback_name)[:200],
            sender_address=sender_address,
            to_addresses=", ".join(to_list),
            cc_addresses=", ".join(cc_list),
            bcc_addresses=", ".join(bcc_list),
            date=timezone.now(),
            text_body=text,
            html_body=html_document,
            assigned_by=AssignedBy.SENT,
            sent_by=user if getattr(user, "pk", None) else None,
            size=len(message.as_bytes()),
            mailbox=mailbox,
            # PRJ-106: written from the page of a subrental, or to a supplier's address.
            supplier=supplier or supplier_for(addresses_of(*to_list, *cc_list)),
            locked=default_lock(project) if locked is None else bool(locked),  # EML-055
        )
        for attachment in attachments or []:
            stored = MailAttachment(
                mail=mail,
                filename=attachment.filename[:255],
                content_type=attachment.content_type[:120],
                size=len(attachment.data),
            )
            stored.file.save(attachment.filename, ContentFile(attachment.data), save=False)
            stored.save()
    log.record(
        direction=Direction.OUTGOING,
        kind=LogKind.PROJECT,
        result=LogResult.SENT,
        sender=mail.sender_label,
        recipients=recipients,
        subject=subject,
        project=project,
        mail=mail,
        user=user,
        message_key=mail.message_key,
        mailbox=mailbox,
    )
    return mail


# --- What can be sent along (EML-025) ---------------------------------------------------------------


def document_choices(rights: Any, project: Project | None = None, user: Any = None) -> list[tuple[str, str]]:
    """The documents of a project the user may send along (EML-025, DOK-008).

    Packlist, price overview and the deployment overview (``deployment``,
    PRJ-081) are made at the moment of sending. The
    documents stored with the project (``documents``) go along as they are –
    ``doc:<id>`` the PDF, ``xml:<id>`` the XRechnung of an invoice. A monthly
    invoice of service cases (DOK-016) only for a ``user`` who may
    read every case it bills – it shows all of them.
    """
    from rentalars.accounts.rights import Module, SpecialRight
    from rentalars.documents.services import may_open_billed

    choices = []
    if rights.can_read(Module.PACKING):
        choices.append(("packlist", _("Packing list (PDF)")))
    may_see_prices = rights.has(SpecialRight.PRICES)
    if may_see_prices:
        choices.append(("prices", _("Price overview (PDF)")))
    if project is not None:
        # PRJ-081: the deployment view, made at the moment of sending as any colleague sees it; not ticked.
        choices.append(("deployment", _("Deployment overview (PDF)")))
        for document in project.documents.order_by("-created_at"):
            if document.is_priced and not may_see_prices:
                continue
            if user is not None and not may_open_billed(document, rights=rights, user=user):
                continue
            choices.append((f"doc:{document.pk}", f"{document.title} {document.number} (PDF)"))
            if document.xml_file:
                choices.append(
                    (
                        f"xml:{document.pk}",
                        f"{document.title} {document.number} ("
                        + ("ZUGFeRD XML" if document.einvoice_syntax == "zugferd" else "XRechnung")
                        + ")",
                    )
                )
    return choices


def note_documents_sent(project: Project, keys: list[str], to: str) -> None:
    """Note on the stored documents that went along when and to whom (DOK-008)."""
    from rentalars.documents.services import mark_sent

    for document in project.documents.filter(pk__in=stored_documents(keys)):
        mark_sent(document, to)


def stored_documents(keys: list[str]) -> list[int]:
    """The IDs of the stored documents among the chosen ones (DOK-008)."""
    return sorted({int(key.split(":", 1)[1]) for key in keys if key.startswith(("doc:", "xml:")) and key[4:].isdigit()})


def content_type_of(name: str) -> str:
    """The media type for a file name; unknown ones are sent as plain data."""
    import mimetypes

    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def chosen_attachments(
    project: Project,
    *,
    rights: Any,
    file_ids: list[Any] = (),  # type: ignore[assignment]
    documents: list[str] = (),  # type: ignore[assignment]
    uploads: list[Any] = (),  # type: ignore[assignment]
    user: Any = None,
) -> list[OutgoingAttachment]:
    """Collect what goes along with a mail: project files, documents made now, uploads (EML-025).

    Files of other projects and documents the user may not see are left out.

    Raises:
        ValidationError: An upload has a type or size that is not allowed (NFA-007).
    """
    from rentalars.core.uploads import validate_document_upload

    result = []
    for file_pk in file_ids:
        try:
            project_file = project.files.filter(pk=int(file_pk)).first()
        except (TypeError, ValueError):
            project_file = None
        if project_file is None:
            continue
        with project_file.file.open("rb") as handle:
            result.append(
                OutgoingAttachment(
                    project_file.original_name, content_type_of(project_file.original_name), handle.read()
                )
            )
    allowed = {key for key, _label in document_choices(rights, project, user)}
    wanted = {document for document in documents if document in allowed}
    for key in sorted(wanted):
        # DOK-008: documents stored with the project go along unchanged.
        if key.startswith(("doc:", "xml:")):
            stored = project.documents.get(pk=int(key[4:]))
            field = stored.file if key.startswith("doc:") else stored.xml_file
            with field.open("rb") as handle:
                name = stored.file_name if key.startswith("doc:") else f"{stored.number}.xml"
                content_type = "application/pdf" if key.startswith("doc:") else "application/xml"
                result.append(OutgoingAttachment(name, content_type, handle.read()))
    if "packlist" in wanted:
        from rentalars.packing import services as packing
        from rentalars.packing.pdf import packing_list_name, render_packlist_pdf

        # PCK-008: every packlist of the project, each as a file of its own.
        for index, packlist in enumerate(packing.packlists_of(project)):
            overview = packing.build_overview(packlist)
            if index and not overview.rows:
                continue
            suffix = f"-{packlist.title}" if index and packlist.title else ""
            result.append(
                OutgoingAttachment(packing_list_name(project, suffix), "application/pdf", render_packlist_pdf(overview))
            )
    if "prices" in wanted:
        from rentalars.projects.price_pdf import render_price_overview_pdf

        result.append(
            OutgoingAttachment(
                download_name("price_overview", project.number, extension="pdf"),
                "application/pdf",
                # PRJ-049: of a whole project only the parts the sender may read.
                render_price_overview_pdf(project, rights=rights, user=user),
            )
        )
    if "deployment" in wanted:
        from rentalars.documents.deployment import deployment_pdf_for_mail, file_name

        # PRJ-081: contact data only as released – the mail leaves the house (PER-019).
        result.append(OutgoingAttachment(file_name(project), "application/pdf", deployment_pdf_for_mail(project)))
    for upload in uploads:
        validate_document_upload(upload)
        result.append(
            OutgoingAttachment(
                upload.name, getattr(upload, "content_type", "") or content_type_of(upload.name), upload.read()
            )
        )
    return result
