# SPDX-License-Identifier: GPL-3.0-or-later
"""The main navigation, filtered by the rights of the user (AUT-015)."""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Module, Rights, SpecialRight


@dataclass(frozen=True)
class Section:
    """A group of pages below one entry of the navigation."""

    #: The module a user must be able to read to see these pages; ``None``: no module needed.
    module: str | None
    #: Name of the page the section starts with.
    url_name: str
    #: Path prefix of the pages that belong to the section.
    prefix: str
    #: ``True``: only for users whose right holds in *all* projects (AUT-017).
    #: A list over the stock of all projects is nothing for somebody who may
    #: see two of them.
    needs_all_projects: bool = False
    #: A special right the user needs as well, e.g. approving times (ZEI-013).
    special: str | None = None
    #: ``True``: the user must be able to write in the module, not only read.
    needs_write: bool = False
    #: ``True``: only for users whose account is a person (AUT-026) – the own pages of "My area".
    needs_person: bool = False
    #: A further module the user must be able to read, e.g. "Reports" over the projects (PRJ-115).
    also_module: str | None = None
    #: ``True``: bookkeeping – gone while Rentalars is not the accounting program (DOK-055).
    bookkeeping: bool = False

    def is_open_to(self, rights: Rights, *, has_person: bool, bookkeeping: bool = True) -> bool:
        """Whether a user with these rights sees the section; ``bookkeeping``: Rentalars keeps the books (DOK-055)."""
        if self.needs_person and not has_person:
            return False
        if self.bookkeeping and not bookkeeping:
            return False
        if self.special is not None and not rights.has(self.special):
            return False
        if self.also_module is not None and not rights.can_read(self.also_module):
            return False
        if self.module is None:
            return True
        if not (rights.can_write(self.module) if self.needs_write else rights.can_read(self.module)):
            return False
        return not (self.needs_all_projects and rights.is_limited_to_assigned_projects(self.module))


@dataclass(frozen=True)
class NavigationEntry:
    """One entry of the main navigation, as it is defined.

    An entry can hold several sections: "Material management" holds the
    products and the material (UIX-013). The entry shows for a user who can
    read at least one of its sections and leads to the first of those.
    """

    label: str | Promise
    #: The sections in the order of the tabs.
    sections: tuple[Section, ...]
    #: Name of the icon in ``static/img/icons.svg``.
    icon: str


@dataclass(frozen=True)
class NavigationLink:
    """An entry as one user sees it: with the addresses that user may open."""

    label: str | Promise
    #: Where the entry leads: the start of its first section the user can read.
    url: str
    icon: str
    #: ``(path prefix, start page)`` of every section the user can read.
    starts: tuple[tuple[str, str], ...]

    def covers(self, path: str) -> int:
        """Return the length of the longest prefix that matches ``path``, or 0."""
        return max((len(prefix) for prefix, _url in self.starts if path.startswith(prefix)), default=0)

    def start_for(self, path: str) -> str:
        """Return the start page of the section a path lies in – where "Back" leads without a trail (UIX-011)."""
        matching = [(len(prefix), url) for prefix, url in self.starts if path.startswith(prefix)]
        return max(matching)[1] if matching else self.url


#: All entries in display order. An entry only shows for users who can at
#: least read one of its sections; modules without access do not appear (AUT-015).
ENTRIES = (
    # EML-042: the inquiries (module "E-mail") are a tab of "Projects"; whoever has the module but no
    # projects still reaches them through this entry.
    NavigationEntry(
        _("Projects"),
        (
            Section(Module.PROJECTS, "projects:list", "/projects/"),
            Section(Module.EMAIL, "mail:unknown_list", "/projects/inquiries/"),
        ),
        "projects",
    ),
    # Overviews over weeks and engpasses (PRJ-028, VFG-012 to VFG-014). The
    # calendar shows every user the projects they may see; the overviews of
    # stock and shortages are for those whose rights hold in all projects.
    NavigationEntry(
        _("Planning"),
        (
            Section(Module.PROJECTS, "schedule:calendar", "/schedule/"),
            # AUT-032: the shortages need the special right to see the availability of material.
            Section(
                Module.PROJECTS,
                "availability:shortages",
                "/shortages/",
                needs_all_projects=True,
                special=SpecialRight.AVAILABILITY,
            ),
            Section(Module.PERSONNEL, "schedule:personnel", "/schedule/personnel/"),
        ),
        "calendar",
    ),
    # Products and material under one roof; the tabs are products, models,
    # items, without product, import (UIX-013).
    NavigationEntry(
        _("Material management"),
        (
            Section(Module.PRODUCTS, "products:list", "/products/"),
            Section(Module.MATERIAL, "material:model_list", "/material/"),
        ),
        "material",
    ),
    # DOK-019, DOK-020: the outgoing documents of all customers – for who sees prices and reads every project,
    # as "Reports" – and the monthly statement of the service cases (DOK-016),
    # for who sees prices and the customers (``documents.statements.may_use``; here by the module "Customers",
    # who reads every project sees it through the first tab). DATEV and Lexware Office stay in "Settings".
    NavigationEntry(
        _("Accounting"),
        (
            Section(
                Module.PROJECTS,
                "documents:outgoing",
                "/accounting/",
                needs_all_projects=True,
                special=SpecialRight.PRICES,
            ),
            Section(
                Module.PROJECTS,
                "documents:statements",
                "/accounting/monthly/",
                special=SpecialRight.PRICES,
                also_module=Module.CUSTOMERS,
            ),
            # The incoming invoices – for who sees purchase prices and reads the material (incoming.access).
            Section(
                Module.MATERIAL,
                "incoming:list",
                "/accounting/incoming/",
                special=SpecialRight.PURCHASE_PRICES,
                bookkeeping=True,
            ),
            # Depreciation, used sale from stock: the Anlagenspiegel and the sales from stock.
            Section(
                Module.MATERIAL,
                "material:asset_register",
                "/accounting/assets/",
                special=SpecialRight.PURCHASE_PRICES,
                bookkeeping=True,
            ),
        ),
        "invoice",
    ),
    NavigationEntry(_("Customers"), (Section(Module.CUSTOMERS, "customers:list", "/customers/"),), "customers"),
    # Approving and the report over everybody's hours are work of personnel planning (UIX-026). The
    # report of one's own hours stays in "My area" for those who see only their own.
    NavigationEntry(
        _("Personnel"),
        (
            Section(Module.PERSONNEL, "personnel:person_list", "/personnel/"),
            Section(
                Module.TIME_TRACKING,
                "timetracking:approval",
                "/times/approval/",
                special=SpecialRight.APPROVE_TIMES,
                needs_write=True,
            ),
            Section(Module.TIME_TRACKING, "timetracking:report", "/times/report/", special=SpecialRight.APPROVE_TIMES),
        ),
        "crew",
    ),
    # PRJ-115, MAT-053: profitability of projects and material – for who may read the module "Reports"
    # (AUT-014) and every project and see prices; the tab of the material asks for the purchase prices as well.
    NavigationEntry(
        _("Reports"),
        (
            Section(
                Module.PROJECTS,
                "projects:report",
                "/reports/",
                needs_all_projects=True,
                special=SpecialRight.PRICES,
                also_module=Module.REPORTS,
            ),
        ),
        "chart",
    ),
    # UIX-026: what everybody does for themselves – the own availability (PER-028), the own times
    # (ZEI-016) and the own personnel data (PER-019).
    NavigationEntry(
        _("My area"),
        (
            # UIX-043: "My area" opens with "Meine Einsätze".
            Section(None, "projects:my_deployments", "/me/", needs_person=True),
            Section(Module.TIME_TRACKING, "timetracking:my_times", "/times/"),
        ),
        "user",
    ),
    # The rental scales are master data and therefore part of the administration (UIX-013); their
    # pages live below /administration/ as well.
    NavigationEntry(
        _("Settings"),
        (Section(Module.ADMINISTRATION, "core:administration", "/administration/"),),
        "settings",
    ),
)


def entries_for(rights: Rights, *, has_person: bool = False, bookkeeping: bool = True) -> list[NavigationLink]:
    """Return the navigation a user with these rights sees; ``has_person``: the account is a person.

    ``bookkeeping``: Rentalars is the accounting program – otherwise the sections of bookkeeping are left out (DOK-055).
    """
    links: list[NavigationLink] = []
    for entry in ENTRIES:
        starts = tuple(
            (section.prefix, reverse(section.url_name))
            for section in entry.sections
            if section.is_open_to(rights, has_person=has_person, bookkeeping=bookkeeping)
        )
        if starts:
            links.append(NavigationLink(entry.label, starts[0][1], entry.icon, starts))
    return links


def current_entry(links: list[NavigationLink], path: str) -> NavigationLink | None:
    """Return the entry a page belongs to: the one with the longest matching prefix."""
    best = max(links, key=lambda link: link.covers(path), default=None)
    return best if best is not None and best.covers(path) else None
