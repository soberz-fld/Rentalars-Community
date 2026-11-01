# SPDX-License-Identifier: GPL-3.0-or-later
"""The signature of mails written in Rentalars (EML-034) and their sender (EML-038).

The company keeps **one** signature for everybody, written as HTML once by
an administrator. Placeholders such as ``{vorname}`` take the data of the
person who writes the mail – first and last name, position, e-mail address
and phone of the account's person (``request.user.person``), and the
company name.

The HTML is cleaned when it is stored and once more after the placeholders
are filled in: a phone number like ``javascript:…`` must not turn into a
link that runs something. A plain-text version for the text part of the mail
is derived from the HTML; nobody has to keep two versions in step.

A signature written without any HTML tags is taken as plain text: its line
breaks are kept.

EML-026: a mailbox may have a signature of its own
(``Mailbox.signature_html``) – written with the same editor, the same
placeholders and cleaned the same way. A mail sent from one of the
mailbox's addresses (its own or an alias) carries it; an empty one means the
common signature (:func:`signature_source`).
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from email.utils import formataddr
from typing import Any

import nh3
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from rentalars.mail.display import ATTRIBUTES, STYLE_PROPERTIES, TAGS, html_to_text


@dataclass(frozen=True)
class Placeholder:
    """A placeholder of the signature, e.g. ``{vorname}`` (EML-034)."""

    token: str
    label: str | Promise


#: The placeholders in the order they are offered. The names are German, as
#: the people who write the signature read them.
PLACEHOLDERS = (
    Placeholder("{vorname}", _("first name")),
    Placeholder("{nachname}", _("last name")),
    Placeholder("{position}", _("position in the company")),
    Placeholder("{email}", _("e-mail address")),
    Placeholder("{telefon}", _("phone")),
    Placeholder("{firma}", _("company name")),
)

#: UIX-029: the English names; both work in the signature, whatever the language.
ENGLISH_TOKENS = {
    "{first_name}": "{vorname}",
    "{last_name}": "{nachname}",
    "{phone}": "{telefon}",
    "{company}": "{firma}",
}
_TOKENS = re.compile(
    "|".join(re.escape(token) for token in [*(placeholder.token for placeholder in PLACEHOLDERS), *ENGLISH_TOKENS])
)


def shown_placeholders() -> list[Placeholder]:
    """The placeholders as the page offers them: the English names while English is active (UIX-029)."""
    from rentalars.core.i18n import is_english

    if not is_english():
        return list(PLACEHOLDERS)
    english = {german: token for token, german in ENGLISH_TOKENS.items()}
    return [Placeholder(english.get(item.token, item.token), item.label) for item in PLACEHOLDERS]


_TAG = re.compile(r"<[a-zA-Z!/][^>]*>")


def clean_signature(source: str) -> str:
    """Clean the HTML of a signature for storing (EML-034).

    Only formatting stays: no scripts, no event handlers, no forms. Links may
    lead to web pages, mail addresses and phone numbers. Plain text without
    any tags keeps its line breaks.
    """
    source = (source or "").strip()
    if not source:
        return ""
    if not _TAG.search(source):
        source = "<br>\n".join(html_module.escape(line, quote=False) for line in source.splitlines())
    return nh3.clean(
        source,
        tags=TAGS,
        attributes=ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "tel"},
        filter_style_properties=STYLE_PROPERTIES,
        strip_comments=True,
    ).strip()


def writer_values(user: Any) -> dict[str, str]:
    """What the placeholders stand for, for the person of an account (EML-034)."""
    from rentalars.core.models import CompanyProfile

    person = getattr(user, "person", None) if getattr(user, "pk", None) else None
    values = {placeholder.token: "" for placeholder in PLACEHOLDERS}
    if person is not None:
        values.update(
            {
                "{vorname}": person.first_name,
                "{nachname}": person.last_name,
                "{position}": person.position,
                "{email}": person.email or getattr(user, "email", "") or "",
                "{telefon}": person.phone,
            }
        )
    values["{firma}"] = CompanyProfile.load().name
    return {token: value or "" for token, value in values.items()}


@dataclass(frozen=True)
class Signature:
    """A signature with the placeholders filled in: HTML and plain text."""

    html: str
    text: str

    def __bool__(self) -> bool:
        return bool(self.html)


def signature_source(mailbox: Any = None, *, common: str | None = None) -> str:
    """The stored HTML of the signature for mails sent from a mailbox's addresses (EML-026).

    Args:
        mailbox: The mailbox the sender address belongs to; ``None`` for the common signature.
        common: The common signature, if loaded already.

    Returns:
        The mailbox's own signature, else the common one (``MailSettings.signature_html``).
    """
    own = (getattr(mailbox, "signature_html", "") or "") if mailbox is not None else ""
    if own.strip():
        return own
    if common is None:
        from rentalars.mail.models import MailSettings

        common = MailSettings.load().signature_html
    return common


def render_signature(user: Any, source: str | None = None, *, mailbox: Any = None) -> Signature:
    """The signature for a writer (EML-034).

    Args:
        user: The account that writes the mail.
        source: The HTML to use (a draft from the editor, cleaned here); the stored signature if ``None``.
        mailbox: EML-026: the mailbox the sender address belongs to – its own signature, if it has one.
    """
    if source is None:
        source = signature_source(mailbox)
    else:
        source = clean_signature(source)
    if not source.strip():
        return Signature("", "")
    values = writer_values(user)
    filled = _TOKENS.sub(
        lambda match: html_module.escape(values[ENGLISH_TOKENS.get(match.group(0), match.group(0))], quote=True),
        source,
    )
    cleaned = clean_signature(filled)
    return Signature(cleaned, html_to_text(cleaned))


def writer_name(user: Any) -> str:
    """The name of the person behind an account; the account's name as a last resort."""
    if not getattr(user, "pk", None):
        return ""
    person = getattr(user, "person", None)
    name = person.name if person is not None else ""
    return name or user.get_full_name() or user.get_username()


def sender_name(user: Any, fallback: str = "") -> str:
    """The display name of the sender: "Max Mustermann | Firma Muster" (EML-038).

    Without a known writer (a mail made by a program) the fallback – the
    sender name of the mailbox settings – or the company name is used.
    """
    from rentalars.core.models import CompanyProfile

    company = CompanyProfile.load().name.strip()
    name = writer_name(user).strip()
    if not name:
        return fallback or company
    return f"{name} | {company}" if company else name


def sender_label(user: Any, address: str, fallback: str = "") -> str:
    """Name and address of the sender as the recipient sees them (EML-038).

    Without an address (no mailbox set up yet) only the name – no empty ``<>``.
    """
    name = sender_name(user, fallback)
    address = (address or "").strip()
    if name and address:
        return f"{name} <{address}>"
    return name or address


def sender_header(user: Any, address: str, fallback: str = "") -> str:
    """The ``From`` header: the display name, encoded if needed, and the mailbox address (EML-038)."""
    return formataddr((sender_name(user, fallback), address))
