# SPDX-License-Identifier: GPL-3.0-or-later
"""A service case as a PDF for the customer – "Überblick" and the open correspondence (PRJ-131).

The requirement: a PDF export of a service case (as a document for the customer) from the tabs "Overview" and "Correspondence" (messages without lock), filed automatically under "Documents".

What the document holds
-----------------------
* The head of the case as the tab "Overview" shows it: number, subject, status, customer (contact and who reported it
  only for who may see customers), who is responsible, when it was created and its description.
* The correspondence as the tab "Correspondence" shows it – but **only the messages without lock** (EML-055): a
  message with lock is read only by those who see prices and calculation and is not meant for the customer. Not part
  of it either, by decision: notes (phone calls and agreements written down for the team), automatic replies and
  delivery failures, the open items, the people taking part, the chat, the follow-up and every price. Attachments
  appear by name only.

The file is stored with the case under "Documents" (a project file, not visible to the crew) and every export makes a
new file with the moment in its name – earlier ones stay. The text is written in the language of the company's
documents (UIX-029). The browser (:func:`rentalars.projects.case_views.case_customer_pdf`) and the API
(``POST /service-cases/{id}/customer-pdf``) call :func:`export_customer_pdf` alike (API-002).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models import QuerySet
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.i18n import for_documents
from rentalars.core.models import CompanyProfile
from rentalars.mail.display import html_to_text
from rentalars.mail.models import Direction, MailKind, ProjectMail
from rentalars.projects import files
from rentalars.projects.models import Project, ProjectFile

#: The longest text of one message in the PDF; a longer one is cut and says so.
MESSAGE_LIMIT = 20_000


@dataclass
class Message:
    """One message of the correspondence as the document shows it."""

    date: Any
    direction: str
    sender: str
    recipients: str
    subject: str
    text: str
    attachments: list[str] = field(default_factory=list)
    shortened: bool = False

    @property
    def is_sent(self) -> bool:
        """Whether we sent it (else: received)."""
        return self.direction == Direction.OUTGOING


def open_messages(case: Project) -> QuerySet[ProjectMail]:
    """The messages of the case that may go to the customer: mails without lock, oldest first.

    Notes, automatic replies and delivery failures are left out whatever their lock says.
    """
    return (
        case.mails.filter(locked=False, direction__in=[Direction.INCOMING, Direction.OUTGOING], kind=MailKind.NORMAL)
        .prefetch_related("attachments")
        .order_by("date", "pk")
    )


def _text_of(mail: ProjectMail) -> str:
    """The text of a mail: the plain part, else the HTML part without its markup."""
    text = (mail.text_body or "").strip()
    if not text and mail.html_body:
        # The same conversion as the mail view: style and script contents and character references are handled.
        text = html_to_text(mail.html_body).strip()
    return text


def messages_of(case: Project) -> list[Message]:
    """The messages for the document, with their attachments by name (pictures inside the text left out)."""
    result = []
    for mail in open_messages(case):
        text = _text_of(mail)
        shortened = len(text) > MESSAGE_LIMIT
        result.append(
            Message(
                date=timezone.localtime(mail.date),
                direction=mail.direction,
                sender=mail.sender_label,
                recipients=(mail.to_addresses or "").strip(),
                subject=mail.subject or "",
                text=text[:MESSAGE_LIMIT],
                attachments=[attachment.filename for attachment in mail.attachments.all() if not attachment.is_inline],
                shortened=shortened,
            )
        )
    return result


def render_html(case: Project, *, with_contacts: bool = False) -> str:
    """The HTML the PDF is made from."""
    from rentalars.documents.pdf import _logo_url
    from rentalars.packing.pdf import _font_url

    with for_documents():
        return render_to_string(
            "projects/case_pdf.html",
            {
                "case": case,
                "with_contacts": with_contacts,
                "messages": messages_of(case),
                "company": CompanyProfile.load(),
                "logo": _logo_url(),
                "made_at": timezone.localtime(),
                "fonts": {
                    "regular": _font_url("barlow-latin-400-normal.woff2"),
                    "semibold": _font_url("barlow-latin-600-normal.woff2"),
                    "condensed": _font_url("barlow-condensed-latin-600-normal.woff2"),
                },
            },
        )


def render_pdf(case: Project, *, with_contacts: bool = False) -> bytes:
    """The case as PDF bytes."""
    from weasyprint import HTML

    return HTML(string=render_html(case, with_contacts=with_contacts), base_url=str(settings.BASE_DIR)).write_pdf()


def file_name(case: Project, moment: Any) -> str:
    """``Servicefall-SF-2026-001-2026-10-23_0936.pdf`` – the case and the moment, so that no export replaces another."""
    with for_documents():
        word = slugify(_("service case"), allow_unicode=False) or "case"
    number = slugify(case.number, allow_unicode=False) or str(case.pk)
    return f"{word}-{number}-{moment:%Y-%m-%d_%H%M%S}.pdf"


def export_customer_pdf(case: Project, *, user: Any, with_contacts: bool = False) -> ProjectFile:
    """Make the PDF for the customer and store it with the case under "Documents".

    Args:
        case: The service case.
        user: Who exports; shown as the one who stored the file.
        with_contacts: Whether contact and reporter go into the document – only if the user may see customers.

    Raises:
        ValidationError: Not a service case, or the case is closed.
    """
    if not case.is_service_case:
        raise ValidationError(_("This is a project, not a service case."))
    moment = timezone.localtime()
    pdf = render_pdf(case, with_contacts=with_contacts)
    name = file_name(case, moment)
    with for_documents():
        title = _("Service case for the customer, as of %(moment)s") % {"moment": f"{moment:%d.%m.%Y %H:%M}"}
    stored = files.add_file(case, ContentFile(pdf, name=name), user=user, title=title, visible_to_crew=False)
    record_event(case, "case.customer_pdf_made", {"file": stored.original_name, "messages": len(messages_of(case))})
    return stored
