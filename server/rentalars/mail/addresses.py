# SPDX-License-Identifier: GPL-3.0-or-later
"""Suggestions for the recipient fields of a mail (EML-037, EML-043).

While somebody types into "To", "CC" or "BCC", the page asks for addresses
that match the part being typed – at least three characters. Suggestions
come from

* customers and their contacts, for who may read the customers;
* the people of the personnel, for who may read the personnel.

Anonymised customers and people, and those without an address, are left out.

Two buttons next to "To" add whole groups at once (EML-043):

* "add crew" – the people planned in the crew of the project
  (:func:`crew_recipients`), with the contact data the writer may see;
* "add customer" – the contact person of the project, else the customer
  (:func:`customer_recipient`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, Rights
from rentalars.mail.parsing import format_address

#: Characters typed before anything is suggested.
MIN_LENGTH = 3
#: Suggestions at most.
LIMIT = 10


@dataclass(frozen=True)
class AddressSuggestion:
    """One address to offer: ``Name <address>`` with where it comes from."""

    name: str
    address: str
    source: str
    detail: str = ""

    @property
    def value(self) -> str:
        """What goes into the field: ``"Name" <address>``."""
        return format_address(self.name, self.address)

    def as_json(self) -> dict[str, str]:
        """The form the type-ahead of the page reads: ``id``, ``label``, ``hint``, ``detail``."""
        return {
            "id": self.value,
            "label": self.value,
            "hint": self.source,
            "detail": self.detail,
            "name": self.name,
            "address": self.address,
        }


def _matches(words: list[str], *fields: str) -> Q:
    """Every word is found in one of the fields: "anna beck" finds Anna Becker."""
    query = Q()
    for word in words:
        any_field = Q()
        for field in fields:
            any_field |= Q(**{f"{field}__icontains": word})
        query &= any_field
    return query


def suggest_addresses(rights: Rights, text: str, *, limit: int = LIMIT) -> list[AddressSuggestion]:
    """Addresses that match a typed text, within the rights of the user (EML-037).

    Args:
        rights: The rights of the user; they decide which sources are searched.
        text: What was typed of one address – name or address, at least three characters.
        limit: The most suggestions to return.
    """
    words = text.strip().strip("<>\"'").split()
    if len("".join(words)) < MIN_LENGTH:
        return []
    found: list[AddressSuggestion] = []
    if rights.can_read(Module.CUSTOMERS):
        from rentalars.customers.models import Contact, Customer

        contacts = (
            Contact.objects.filter(customer__anonymised_at__isnull=True)
            .exclude(email="")
            .filter(_matches(words, "name", "email", "customer__name"))
            .select_related("customer")
            .order_by("name")[:limit]
        )
        found += [
            AddressSuggestion(contact.name, contact.email, _("Contact"), contact.customer.name) for contact in contacts
        ]
        customers = (
            Customer.objects.filter(anonymised_at__isnull=True)
            .exclude(email="")
            .filter(_matches(words, "name", "email"))
            .order_by("name")[:limit]
        )
        found += [AddressSuggestion(customer.name, customer.email, _("Customer")) for customer in customers]
    if rights.can_read(Module.PERSONNEL):
        from rentalars.personnel.models import Person

        people = (
            Person.objects.filter(is_active=True, anonymised_at__isnull=True)
            .exclude(email="")
            .filter(_matches(words, "first_name", "last_name", "email"))
            .order_by("last_name", "first_name")[:limit]
        )
        found += [AddressSuggestion(person.name, person.email, _("Personnel"), person.position) for person in people]
    unique: dict[str, AddressSuggestion] = {}
    for suggestion in found:
        unique.setdefault(suggestion.address.lower(), suggestion)
    return list(unique.values())[:limit]


def crew_recipients(project: Any, *, rights: Rights, user: Any) -> list[str]:
    """The addresses of the people planned in the crew of a project, in the order of the plan (EML-043).

    Planned means: a crew line with a person whose request was not declined.
    A whole project brings the crew of the parts the writer may read, as its
    correspondence shows their mails (PRJ-044, PRJ-049); a part only its own.

    The rule of the deployment view applies (PER-019): who may edit the
    project or read the personnel gets every address; anybody else only
    those the people released for their colleagues. Inactive and anonymised
    people are left out; every address comes once.
    """
    from rentalars.projects.access import ProjectAccess, readable_projects
    from rentalars.projects.models import CrewLine, Project, RequestStatus

    projects = [project.pk]
    if project.parent_id is None and project.has_subprojects:
        parts = readable_projects(rights, user, Project.objects.filter(parent_id=project.pk))
        projects += list(parts.values_list("pk", flat=True))
    sees_all = getattr(project, "access", ProjectAccess.READ) >= ProjectAccess.EDIT or rights.can_read(Module.PERSONNEL)
    lines = (
        CrewLine.objects.filter(project_id__in=projects, person__isnull=False)
        .exclude(request_status=RequestStatus.DECLINED)
        .select_related("person")
        .order_by("start", "position", "id")
    )
    found: dict[str, str] = {}
    for line in lines:
        person = line.person
        if not person.email or not person.is_active or person.anonymised_at is not None:
            continue
        if sees_all or person.share_email:
            found.setdefault(person.email.lower(), format_address(person.name, person.email))
    return list(found.values())


def customer_recipient(project: Any) -> str:
    """The address for "add customer": the contact person of the project, else the customer's (EML-043).

    A part without a contact person of its own takes the one of its whole
    project; customer and billing are always those of the whole project.
    """
    contact = project.contact
    if contact is None and project.parent_id is not None:
        contact = project.parent.contact
    if contact is not None and contact.email:
        return format_address(contact.name, contact.email)
    customer = project.customer
    if customer is not None and customer.email and getattr(customer, "anonymised_at", None) is None:
        return format_address(customer.name, customer.email)
    return ""
