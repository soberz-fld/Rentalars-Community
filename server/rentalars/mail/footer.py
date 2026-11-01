# SPDX-License-Identifier: GPL-3.0-or-later
"""The footer of every mail Rentalars sends by itself (EML-045).

Whoever gets a mail from Rentalars should see where it comes from: "This
message was sent automatically by Rentalars for <company>: <address of the
installation>". That holds for every *system mail* – notifications, the
invitation, the password link, deployment requests and the replies to
answers by mail (PER-032), the test mail of the self-check, reports of
errors and of tasks in the background.

The mails of the correspondence are not system mails: a person writes them
in a project, and they carry that person's signature (EML-034). They go out
through the outgoing mailbox by ``mail.sending``, not through Django's mail
backend.

One place
---------
Every system mail passes the mail backend of Rentalars
(:class:`rentalars.mail.backends.LoggingEmailBackend`, EML-039), so the
backend adds the footer (:func:`add_footer`) just before sending – whoever
built the mail, Django's password reset included. The text part gets it
behind the usual signature separator ``-- ``; an HTML part – or a mail that
is HTML only – gets it as a last paragraph inside ``<body>``. A message gets
the footer once, even if it is sent again.

The company is the name of the company profile (ADM-001); the address is
``[rentalars] url`` of the configuration (``settings.RENTALARS_URL``). The
footer is written in the language the mail is written in; outside of a
request in the language of the installation.
"""

from __future__ import annotations

import re
from contextlib import nullcontext
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.message import EmailAlternative
from django.db import DatabaseError
from django.utils import translation
from django.utils.html import escape
from django.utils.translation import gettext as _

#: Set on a message once it has the footer.
_DONE = "_rentalars_footer"
#: The signature separator of RFC 3676: mail programs fold away or leave out what follows when quoting.
SEPARATOR = "-- "
_BODY_END = re.compile(r"</body\s*>", re.IGNORECASE)


def _company_name() -> str:
    from rentalars.core.models import CompanyProfile

    try:
        return (CompanyProfile.load().name or "").strip()
    except DatabaseError:
        # Without the database a report of the problem still goes out – without the company.
        return ""


def _language() -> Any:
    """The language of the mail; outside of a request with translations switched off, the installation's."""
    return nullcontext() if translation.get_language() else translation.override(settings.LANGUAGE_CODE)


def footer_text(company: str | None = None) -> str:
    """``This message was sent automatically by Rentalars for Musterverleih GmbH: https://…`` (EML-045)."""
    company = _company_name() if company is None else company
    url = settings.RENTALARS_URL
    with _language():
        if company:
            return _("This message was sent automatically by Rentalars for %(company)s: %(url)s") % {
                "company": company,
                "url": url,
            }
        return _("This message was sent automatically by Rentalars: %(url)s") % {"url": url}


def footer_html(company: str | None = None) -> str:
    """The footer as the last paragraph of an HTML mail, with the address as a link (EML-045)."""
    company = _company_name() if company is None else company
    url = settings.RENTALARS_URL
    link = f'<a href="{escape(url)}" style="color:#0b5cad">{escape(url)}</a>'
    with _language():
        if company:
            text = _("This message was sent automatically by Rentalars for %(company)s: %(url)s") % {
                "company": escape(company),
                "url": link,
            }
        else:
            text = _("This message was sent automatically by Rentalars: %(url)s") % {"url": link}
    return (
        '<p style="margin:24px 0 0;padding-top:12px;border-top:1px solid #d0d7de;color:#57606a;font-size:13px">'
        f"{text}</p>"
    )


def with_text_footer(body: str, footer: str) -> str:
    """The text of a mail with the footer behind the signature separator."""
    return f"{(body or '').rstrip()}\n\n{SEPARATOR}\n{footer}\n"


def with_html_footer(document: str, footer: str) -> str:
    """An HTML mail with the footer as its last paragraph – inside ``<body>`` if there is one."""
    ends = list(_BODY_END.finditer(document or ""))
    if not ends:
        return f"{document or ''}\n{footer}"
    at = ends[-1].start()
    return f"{document[:at]}{footer}\n{document[at:]}"


def add_footer(message: EmailMessage) -> None:
    """Add the footer to a system mail: to the text and to every HTML part, once (EML-045)."""
    if getattr(message, _DONE, False):
        return
    company = _company_name()
    text, html = footer_text(company), footer_html(company)
    if message.content_subtype == "html":
        message.body = with_html_footer(message.body, html)
    else:
        message.body = with_text_footer(message.body, text)
    alternatives = getattr(message, "alternatives", None)
    if alternatives:
        message.alternatives = [
            EmailAlternative(with_html_footer(content, html), mimetype)
            if mimetype == "text/html" and isinstance(content, str)
            else EmailAlternative(content, mimetype)
            for content, mimetype in alternatives
        ]
    setattr(message, _DONE, True)
