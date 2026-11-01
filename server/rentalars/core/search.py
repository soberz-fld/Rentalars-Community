# SPDX-License-Identifier: GPL-3.0-or-later
"""The global search across modules (UIX-002).

The search only looks into modules the user may read; results from other
modules are not merely hidden, they are never queried.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module, Rights
from rentalars.customers.models import Customer
from rentalars.material.filters import search_items
from rentalars.material.models import MaterialItem
from rentalars.personnel.models import Person
from rentalars.products.models import Product
from rentalars.projects import numbers as project_numbers
from rentalars.projects.access import visible_projects
from rentalars.projects.family_labels import part_of

#: How many hits are shown per kind of record.
RESULTS_PER_KIND = 10


@dataclass
class SearchHit:
    """One search result."""

    title: str
    subtitle: str
    url: str
    #: Primary key of the record, for callers of the API.
    id: int = 0


@dataclass
class SearchGroup:
    """The hits of one kind of record, e.g. all matching customers."""

    label: str
    hits: list[SearchHit] = field(default_factory=list)
    #: Address of the full list with the same search, if there are more hits.
    more_url: str = ""
    #: Machine-readable kind of the records: "projects", "customers", …
    kind: str = ""


def global_search(text: str, rights: Rights, user: Any = None) -> list[SearchGroup]:
    """Search projects, customers, products, material and people for ``text``.

    Material is found by ID, serial number and article name; products by
    article number, name and GTIN; people by name.

    Projects are searched only among those the user may see (AUT-016,
    acceptance scenario 6). Somebody limited to assigned projects neither
    finds a project through its customer nor reads the customer's name in
    the result (AUT-023).

    Args:
        text: What was typed.
        rights: The rights of the user.
        user: The user; needed to know the assigned projects.
    """
    text = text.strip()
    if not text:
        return []
    groups: list[SearchGroup] = []

    if rights.can_read(Module.PROJECTS):
        knows_customers = rights.level_everywhere(Module.PROJECTS) >= Level.READ or rights.can_read(Module.CUSTOMERS)
        # PRJ-044: the name of a whole project finds its parts as well.
        # ADM-012, ADM-014: the former number (P-2026-0042, now 2026-0042 again) finds the project too.
        condition = (
            project_numbers.matching(text)
            | Q(name__icontains=text)
            | Q(venue__icontains=text)
            | Q(parent__name__icontains=text)
        )
        # PRJ-122: the customer's name shows in every role, so it finds the project in every role.
        condition |= Q(customer__name__icontains=text)
        projects = (
            visible_projects(rights, user).filter(condition).select_related("customer", "parent")[:RESULTS_PER_KIND]
        )
        groups.append(
            SearchGroup(
                _("Projects"),
                [
                    SearchHit(
                        f"{project.number} {project.name}",
                        # PRJ-044: a part says whose part it is.
                        " · ".join(
                            note
                            for note in (
                                # PRJ-090: a service case says so.
                                _("service case") if project.is_service_case else part_of(project),
                                project.customer_name
                                if knows_customers
                                else (project.customer.name if project.customer_id else project.venue),
                            )
                            if note
                        ),
                        reverse("projects:overview", args=[project.pk]),
                        project.pk,
                    )
                    for project in projects
                ],
                reverse("projects:list") + f"?q={text}",
                "projects",
            )
        )

    if rights.can_read(Module.CUSTOMERS):
        customers = Customer.objects.filter(
            Q(name__icontains=text) | Q(number__icontains=text) | Q(city__icontains=text) | Q(email__icontains=text)
        )[:RESULTS_PER_KIND]
        groups.append(
            SearchGroup(
                _("Customers"),
                [
                    SearchHit(
                        customer.name,
                        f"{customer.number} {customer.city}".strip(),
                        reverse("customers:detail", args=[customer.pk]),
                        customer.pk,
                    )
                    for customer in customers
                ],
                reverse("customers:list") + f"?q={text}",
                "customers",
            )
        )

    if rights.can_read(Module.PRODUCTS):
        products = Product.objects.filter(
            Q(article_number__icontains=text) | Q(name__icontains=text) | Q(gtin__icontains=text)
        )[:RESULTS_PER_KIND]
        groups.append(
            SearchGroup(
                _("Products"),
                [
                    SearchHit(
                        f"{product.article_number} {product.name}",
                        "",
                        reverse("products:detail", args=[product.pk]),
                        product.pk,
                    )
                    for product in products
                ],
                reverse("products:list") + f"?q={text}",
                "products",
            )
        )

    if rights.can_read(Module.MATERIAL):
        items = search_items(MaterialItem.objects.select_related("material_model"), text)[:RESULTS_PER_KIND]
        groups.append(
            SearchGroup(
                _("Material"),
                [
                    SearchHit(
                        f"{item.display_id} {item.material_model.name}",
                        item.serial_number,
                        reverse("material:item_detail", args=[item.pk]),
                        item.pk,
                    )
                    for item in items
                ],
                reverse("material:item_list") + f"?q={text}",
                "material_items",
            )
        )
    if rights.can_read(Module.PERSONNEL):
        people = Person.objects.filter(
            Q(first_name__icontains=text) | Q(last_name__icontains=text) | Q(company__icontains=text)
        )[:RESULTS_PER_KIND]
        groups.append(
            SearchGroup(
                _("People"),
                [
                    SearchHit(
                        person.name,
                        person.get_kind_display(),
                        reverse("personnel:person_detail", args=[person.pk]),
                        person.pk,
                    )
                    for person in people
                ],
                reverse("personnel:person_list") + f"?q={text}",
                "people",
            )
        )
    if rights.can_read(Module.CUSTOMERS):
        from rentalars.customers.models import Venue

        venues = Venue.objects.filter(Q(name__icontains=text) | Q(city__icontains=text))[:RESULTS_PER_KIND]
        groups.append(
            SearchGroup(
                _("Venues"),
                [
                    SearchHit(venue.name, venue.city, reverse("customers:venue_detail", args=[venue.pk]), venue.pk)
                    for venue in venues
                ],
                reverse("customers:venue_list") + f"?q={text}",
                "venues",
            )
        )
    # EML-022: mails, only of projects the user may read and only with the correspondence right (EML-029).
    if rights.can_read(Module.PROJECTS):
        from rentalars.mail.services import search_mails

        mails = search_mails(rights, user, text, limit=RESULTS_PER_KIND)
        groups.append(
            SearchGroup(
                _("Mails"),
                [
                    SearchHit(
                        mail.subject or str(_("(no subject)")),
                        f"{mail.project.number} · {mail.sender_label}",
                        reverse("mail:detail", args=[mail.project_id, mail.pk]),
                        mail.pk,
                    )
                    for mail in mails
                ],
                "",
                "mails",
            )
        )
    return [group for group in groups if group.hits]
