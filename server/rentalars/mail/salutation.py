# SPDX-License-Identifier: GPL-3.0-or-later
"""The greeting line a mail to a contact person begins with (EML-024, KND-004: greeting per contact).

The salutation of mails is adjustable per contact: every contact has its greeting (``customers.greetings``). Where
Rentalars starts a mail – the mail form ("Mail schreiben", also from a document with "Senden"), the reply draft of
the AI – the greeting of the contact the mail goes to stands at its top. Only a mail to exactly one address that
belongs to a contact of the project's customer gets one; any other recipient (several addresses, a supplier, an
address nobody knows) changes nothing.
"""

from __future__ import annotations

from email.utils import getaddresses
from typing import Any

from rentalars.customers import greetings
from rentalars.customers.models import Contact


def contact_of(project: Any, to: str) -> Contact | None:
    """The contact of the project's customer that is the only recipient in ``to``; else ``None``."""
    addresses = {address.strip().lower() for _name, address in getaddresses([to or ""]) if address.strip()}
    if len(addresses) != 1 or project.customer_id is None:
        return None
    return greetings.contact_for_address(addresses.pop(), customer_id=project.customer_id)


def opening_line(project: Any, to: str, *, text_answered: str = "") -> str:
    """The greeting for a mail from ``project`` to ``to``, or "" when the recipient is no known contact.

    ``text_answered``: the text of the mail being answered; its language (German or English) is the language of the
    greeting, else the language of the company's documents.
    """
    contact = contact_of(project, to)
    if contact is None:
        return ""
    language = greetings.guess_language(text_answered) if text_answered.strip() else None
    return greetings.greeting(contact, language)
