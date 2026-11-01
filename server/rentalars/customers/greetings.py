# SPDX-License-Identifier: GPL-3.0-or-later
"""The greeting line of a mail to a contact person (KND-004: greeting per contact).

The requirement: a new contact person of a customer has a first and a last name apart, and the salutation of mails is
adjustable per contact.

Every contact has a ``greeting_style``:

* **formal** (the default): "Sehr geehrte Frau Berg," / "Sehr geehrter Herr Berg,". The gender comes from the
  salutation of the contact ("Frau", "Herr", "Ms", "Mr" …). With a title ("Dr", "Prof") and no gender the greeting
  is "Guten Tag Dr. Berg,", because "Herr" or "Frau" cannot be guessed; with the gender and the title it is
  "Sehr geehrte Frau Dr. Berg,". Without a salutation it is "Guten Tag Anna Berg,".
* **personal**: "Hallo Anna,". A contact without a first name gets the formal greeting.
* **custom**: the text of ``greeting_text`` as typed ("Liebe Anna,"). Empty: the formal greeting.

:func:`greeting` returns the whole line including the comma, in German or English (the language of the company's
documents unless asked otherwise). :func:`contact_for_address` finds the contact a mail goes to,
:func:`greeting_for_address` the line for it, and :func:`guess_language` the language of a mail being answered.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils import translation
from django.utils.translation import pgettext

from rentalars.customers.models import GreetingStyle
from rentalars.customers.names import first_name_for_greeting, is_title, join_name, tidy

if TYPE_CHECKING:
    from rentalars.customers.models import Contact


#: Salutations that name a woman or a man (compared in lower case, without dots).
_FEMALE = frozenset({"frau", "fr", "ms", "mrs", "miss", "mme", "madame"})
_MALE = frozenset({"herr", "hr", "mr", "mister", "monsieur"})


def _key(word: str) -> str:
    return word.casefold().replace(".", "")


def _read_salutation(salutation: str) -> tuple[str, list[str]]:
    """The gender ("f", "m" or "") and the titles a salutation names: "Frau Dr." is ("f", ["Dr."])."""
    gender = ""
    titles: list[str] = []
    for word in tidy(salutation).replace(",", " ").split():
        if _key(word) in _FEMALE:
            gender = gender or "f"
        elif _key(word) in _MALE:
            gender = gender or "m"
        elif is_title(word):
            titles.append(word + "." if _key(word) in {"dr", "prof"} and not word.endswith(".") else word)
    return gender, titles


def _address_form(gender: str, name: str) -> str:
    """The address form with Ms or Mr ("Sehr geehrte Frau Berg,") in the current language."""
    if gender == "f":
        return pgettext("greeting", "Dear Ms %(name)s,") % {"name": name}
    return pgettext("greeting", "Dear Mr %(name)s,") % {"name": name}


def formal(contact: Contact, language: str) -> str:
    """The formal greeting: "Sehr geehrte Frau Berg," – or "Guten Tag Anna Berg," where the gender is unknown."""
    gender, titles = _read_salutation(contact.salutation)
    last = tidy(contact.last_name) or tidy(contact.name)
    with translation.override(language):
        if titles:
            name = " ".join([*titles, last])
            # English has one form for all ("Dear Dr. Berg,"); German adds Herr or Frau where it is known.
            if gender and language != "en":
                return _address_form(gender, name)
            return pgettext("greeting", "Dear %(name)s,") % {"name": name}
        if gender:
            return _address_form(gender, last)
        return pgettext("greeting", "Dear %(name)s,") % {
            "name": join_name(contact.first_name, last) or tidy(contact.name)
        }


def personal(contact: Contact, language: str) -> str:
    """The greeting with the first name: "Hallo Anna,"; the formal one where there is no first name."""
    first = first_name_for_greeting(contact.first_name)
    if not first:
        return formal(contact, language)
    with translation.override(language):
        return pgettext("greeting", "Hello %(name)s,") % {"name": first}


def greeting(contact: Contact, language: str | None = None) -> str:
    """The greeting line for a contact, with the comma; ``language`` "de" or "en" (the documents' language if None)."""
    if language is None:
        from rentalars.core.i18n import document_language

        language = document_language()
    if contact.greeting_style == GreetingStyle.CUSTOM and tidy(contact.greeting_text):
        return contact.greeting_text.strip()
    if contact.greeting_style == GreetingStyle.PERSONAL:
        return personal(contact, language)
    return formal(contact, language)


def generic_greeting(language: str | None = None) -> str:
    """The greeting for somebody who is no known contact: "Guten Tag," / "Hello,"."""
    if language is None:
        from rentalars.core.i18n import document_language

        language = document_language()
    with translation.override(language):
        return pgettext("greeting", "Hello,")


def neutral_greeting(language: str | None = None) -> str:
    """The formal greeting for somebody whose name is not known: "Sehr geehrte Damen und Herren," / "Dear Sir or Madam,"."""
    if language is None:
        from rentalars.core.i18n import document_language

        language = document_language()
    with translation.override(language):
        return pgettext("greeting", "Dear Sir or Madam,")


def contact_for_address(address: str, *, customer_id: int | None = None) -> Contact | None:
    """The contact with this e-mail address; of this customer if one is named, else of any customer.

    Contacts of anonymised customers do not exist any more (KND-010). Several contacts with the same address:
    the primary one, then the oldest.
    """
    from rentalars.customers.models import Contact

    address = (address or "").strip()
    if not address:
        return None
    contacts = Contact.objects.filter(email__iexact=address).select_related("customer")
    if customer_id is not None:
        contacts = contacts.filter(customer_id=customer_id)
    return contacts.order_by("-is_primary", "pk").first()


def greeting_for_address(address: str, *, customer_id: int | None = None, language: str | None = None) -> str:
    """The greeting for a mail to this address: the contact's, or "" if no contact has the address."""
    contact = contact_for_address(address, customer_id=customer_id)
    return greeting(contact, language) if contact is not None else ""


_GERMAN_WORDS = frozenset(
    {"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "bitte", "danke", "wir", "sie", "ich", "für", "mit",
     "auf", "vielen", "grüße", "freundlichen", "hallo", "guten", "tag", "angebot", "anfrage", "herr", "frau", "sehr",
     "geehrte", "geehrter", "wäre", "haben", "können", "wird", "zu", "von", "im", "den", "dem"}
)  # fmt: skip
_ENGLISH_WORDS = frozenset(
    {"the", "and", "is", "not", "a", "an", "please", "thanks", "thank", "we", "you", "i", "for", "with", "on",
     "regards", "best", "kind", "hello", "dear", "hi", "quote", "request", "would", "have", "can", "will", "to", "of",
     "in", "at", "your", "our", "this", "that", "be", "are"}
)  # fmt: skip


def guess_language(text: str, default: str | None = None) -> str:
    """Whether a mail is German ("de") or English ("en"); ``default`` (else the documents' language) if unclear."""
    words = re.findall(r"[a-zäöüß]+", (text or "").casefold())
    german = sum(word in _GERMAN_WORDS for word in words)
    english = sum(word in _ENGLISH_WORDS for word in words)
    if german > english:
        return "de"
    if english > german:
        return "en"
    if default:
        return default
    from rentalars.core.i18n import document_language

    return document_language()
