# SPDX-License-Identifier: GPL-3.0-or-later
"""Sending a document without a project by mail.

A document of a project goes out from the correspondence of the project (DOK-008). A free document has no project to
store the mail with, so this sends it through the outgoing mailbox with the PDF (and, if wished, the XRechnung)
attached, notes it in the mail log (EML-039) and on the document ("sent on … to …"), and records the event at the
customer.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.forms import StyledForm
from rentalars.core.i18n import for_documents
from rentalars.customers import greetings
from rentalars.documents import services
from rentalars.documents.models import Document, DocumentKind
from rentalars.mail import log, sending
from rentalars.mail.models import Direction, LogKind, LogResult, MailSettings, message_key
from rentalars.mail.senders import default_sender
from rentalars.mail.signature import Signature, render_signature, sender_header


class SendForm(StyledForm):
    """Recipient, subject and text of the mail with a free document."""

    to = forms.CharField(label=gettext_lazy("To"), max_length=500)
    cc = forms.CharField(label=gettext_lazy("Cc"), required=False, max_length=500)
    bcc = forms.CharField(label=gettext_lazy("Bcc"), required=False, max_length=500)
    subject = forms.CharField(label=gettext_lazy("Subject"), max_length=300)
    body = forms.CharField(label=gettext_lazy("Text"), widget=forms.Textarea(attrs={"rows": 8}))
    signature = forms.BooleanField(
        label=gettext_lazy("With the signature of the company"), required=False, initial=True
    )
    xml = forms.BooleanField(label=gettext_lazy("Send the XRechnung along"), required=False)

    def __init__(self, *args: Any, document: Document | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if document is not None and not document.xml_file:
            del self.fields["xml"]
        elif document is not None and document.einvoice_syntax == "zugferd":
            # DOK-044: the PDF carries the invoice data; the XML apart is a copy, not preselected.
            self.fields["xml"].label = gettext_lazy("Send the XML of the invoice apart, too")

    def clean_subject(self) -> str:
        """One line: white space and line breaks in the subject become single blanks."""
        return " ".join(self.cleaned_data["subject"].split())


def xml_preselected(document: Document) -> bool:
    """DOK-044: whether the XML of an invoice goes along with the mail by default.

    An XRechnung goes with its XML when the customer has a buyer reference (the Leitweg-ID of an authority is one): the
    recipient reads the XML, not the PDF. Otherwise it can be chosen. A ZUGFeRD PDF carries its data inside; the XML apart
    would only be a second copy, so it is not preselected either.
    """
    if not document.xml_file or document.einvoice_syntax == "zugferd":
        return False
    customer = document.customer
    return bool(customer is not None and customer.buyer_reference)


def initial_for(document: Document) -> dict[str, Any]:
    """The mail as proposed: to the customer's address, with the document named in subject and text.

    The text starts with the greeting of the contact whose address it goes to (KND-004), else the general one.
    """
    to = document.content.get("recipient_email") or (document.customer.email if document.customer_id else "")
    with for_documents() as language:
        subject = f"{document.title} {document.number}"
        greeting = greetings.greeting_for_address(to, customer_id=document.customer_id, language=language)
        greeting = greeting or greetings.generic_greeting(language)
        if document.kind == DocumentKind.OFFER:
            sentence = _("Please find our offer attached.")
        elif document.kind == DocumentKind.INVOICE:
            sentence = _("Please find our invoice attached.")
        else:
            sentence = _("Please find the attached document.")
        body = f"{greeting}\n\n{sentence}\n\n{_('Kind regards')}"
    return {"to": to, "subject": subject, "body": body, "signature": True, "xml": xml_preselected(document)}


def send_document_mail(
    document: Document,
    *,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    with_signature: bool = True,
    with_xml: bool = False,
    user: Any = None,
) -> None:
    """Send the PDF of a document without a project through the outgoing mailbox and note it as sent.

    Raises:
        ValidationError: The customer was anonymised, sending is not set up, an address is not valid, or the
            server refused the mail.
    """
    if document.customer_id and document.customer.is_anonymised:
        # The mail would take the personal data of the document to an address nobody has any more.
        raise ValidationError(_("This customer was anonymised; the document is not sent."))
    chosen = default_sender(None)
    if chosen is None or not chosen.mailbox.can_send or not chosen.address:
        raise ValidationError(_("Sending is not set up. An administrator fills in the mailbox first."))
    mailbox, sender_address = chosen.mailbox, chosen.address
    to_list = sending._checked("to", to)
    cc_list = sending._checked("cc", cc)
    bcc_list = sending._checked("bcc", bcc)
    if not to_list:
        raise ValidationError({"to": _("Enter at least one recipient.")})
    # A line break in the subject would be refused as a header: the subject is one line.
    subject = " ".join(subject.split()) or f"{document.title} {document.number}"
    signature = render_signature(user, mailbox=chosen.owner) if with_signature else Signature("", "")
    text, html_document = sending.mail_parts(body, signature)

    message = EmailMessage()
    message["From"] = sender_header(user, sender_address, MailSettings.load().sender_name)
    message["To"] = ", ".join(to_list)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    if bcc_list:
        message["Bcc"] = ", ".join(bcc_list)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=sender_address.rsplit("@", 1)[-1])
    message.set_content(text)
    if html_document:
        message.add_alternative(html_document, subtype="html")
    with document.file.open("rb") as handle:
        message.add_attachment(handle.read(), maintype="application", subtype="pdf", filename=document.file_name)
    if with_xml and document.xml_file:
        with document.xml_file.open("rb") as handle:
            message.add_attachment(
                handle.read(), maintype="application", subtype="xml", filename=f"{document.number}.xml"
            )

    recipients = to_list + cc_list + bcc_list
    key = message_key(message["Message-ID"])
    try:
        sending._send(mailbox, message)
    except ValidationError as error:
        log.record(
            direction=Direction.OUTGOING,
            kind=LogKind.SYSTEM,
            result=LogResult.FAILED,
            sender=sender_address,
            mailbox=mailbox,
            recipients=recipients,
            subject=subject,
            user=user,
            message_key=key,
            detail=" ".join(error.messages),
        )
        raise
    log.record(
        direction=Direction.OUTGOING,
        kind=LogKind.SYSTEM,
        result=LogResult.SENT,
        sender=sender_address,
        mailbox=mailbox,
        recipients=recipients,
        subject=subject,
        user=user,
        message_key=key,
    )
    services.mark_sent(document, ", ".join(to_list))
