# SPDX-License-Identifier: GPL-3.0-or-later
"""What is bookkeeping, and that it is hidden while Rentalars is not the accounting program (DOK-055).

* The list of pages and API addresses (``documents.bookkeeping``) names only addresses that exist, and every page
  below "accounting/" is either bookkeeping or on the list of what stays – a new tab cannot be forgotten.
* The sections of the navigation and the tabs of "Buchhaltung" follow the setting.
"""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, get_resolver

from rentalars.accounts.rights import Module, Rights, SpecialRight
from rentalars.core.models import SystemSettings
from rentalars.core.navigation import entries_for
from rentalars.documents import bookkeeping
from rentalars.documents import outgoing as outgoing_tabs
from tests.helpers import RentalarsTestCase

#: Pages below "accounting/" that stay while Rentalars is not the accounting program: the outgoing documents (also
#: the free documents), the monthly statement of the service cases.
STAYS = frozenset(
    {
        "documents:outgoing",
        "documents:outgoing_download",
        "documents:free_new",
        "documents:free_edit",
        "documents:free_line_add",
        "documents:free_line_edit",
        "documents:free_line_delete",
        "documents:free_line_move",
        "documents:free_preview",
        "documents:free_issue",
        "documents:free_delete",
        "documents:free_document",
        "documents:free_send",
        "documents:free_cancel",
        "documents:check",  # the button of an outgoing invoice: check the e-invoice again
        "documents:statements",
        "documents:statement_create",
        "documents:statement",
        "documents:statement_delete",
        "documents:statement_job",
    }
)


def page_names() -> dict[str, str]:
    """``{view name: route}`` of every page and API address, as ``namespace:name``."""
    found: dict[str, str] = {}

    def walk(patterns: list, namespace: str, route: str) -> None:
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                inner = f"{namespace}{pattern.namespace}:" if pattern.namespace else namespace
                walk(pattern.url_patterns, inner, route + str(pattern.pattern))
            elif isinstance(pattern, URLPattern) and pattern.name:
                found[f"{namespace}{pattern.name}"] = route + str(pattern.pattern)

    walk(get_resolver().url_patterns, "", "")
    return found


class ListTests(RentalarsTestCase):
    def test_every_name_on_the_list_exists(self) -> None:
        names = page_names()
        for pattern in bookkeeping.PAGES | bookkeeping.API:
            matching = [name for name in names if bookkeeping.is_bookkeeping(name) and _matches(pattern, name)]
            self.assertTrue(matching, f"{pattern} names no page or API address")

    def test_every_page_below_accounting_is_bookkeeping_or_stays(self) -> None:
        checked = 0
        for name, route in page_names().items():
            if name.startswith("api:") or "accounting/" not in route:
                continue
            if route.endswith("accounting/") or route.startswith(("administration/accounting", "documents/")):
                continue  # the settings of Lexware Office and DATEV stay (they hide their own parts)
            checked += 1
            self.assertTrue(
                bookkeeping.is_bookkeeping(name) or name in STAYS,
                f"{name} ({route}) is neither bookkeeping nor listed as staying – decide (DOK-055)",
            )
        self.assertGreater(checked, 40)

    def test_the_outgoing_documents_and_the_statements_are_not_bookkeeping(self) -> None:
        for name in STAYS:
            self.assertFalse(bookkeeping.is_bookkeeping(name), name)
        self.assertFalse(bookkeeping.is_bookkeeping("api:accounting-documents"))
        self.assertFalse(bookkeeping.is_bookkeeping("api:accounting-lexware-transfers"))

    def test_the_incoming_invoices_the_bank_and_the_euer_are(self) -> None:
        for name in (
            "incoming:list",
            "incoming:capture",
            "documents:open_items",
            "documents:bank_upload",
            "documents:euer",
            "documents:archive_verify",
            "material:asset_register",
            "material:sale_detail",
            "projects:legacy_batch",
            "api:incoming-invoice-book",
            "api:accounting-euer",
            "api:stock-sale-cancel",
            "api:legacy-import-confirm",
        ):
            self.assertTrue(bookkeeping.is_bookkeeping(name), name)


def _matches(pattern: str, name: str) -> bool:
    return name.startswith(pattern[:-1]) if pattern.endswith("*") else name == pattern


class NavigationTests(RentalarsTestCase):
    def accountant(self) -> Rights:
        return Rights.everything()

    def test_the_sections_of_bookkeeping_follow_the_setting(self) -> None:
        labels_on = [link.label for link in entries_for(self.accountant(), bookkeeping=True)]
        self.assertIn("Buchhaltung", [str(label) for label in labels_on])
        on = next(link for link in entries_for(self.accountant()) if str(link.label) == "Buchhaltung")
        off = next(
            link for link in entries_for(self.accountant(), bookkeeping=False) if str(link.label) == "Buchhaltung"
        )
        self.assertIn("/accounting/incoming/", [prefix for prefix, _start in on.starts])
        self.assertNotIn("/accounting/incoming/", [prefix for prefix, _start in off.starts])
        self.assertNotIn("/accounting/assets/", [prefix for prefix, _start in off.starts])
        self.assertIn("/accounting/", [prefix for prefix, _start in off.starts])

    def test_whoever_has_only_bookkeeping_loses_the_whole_entry(self) -> None:
        rights = Rights(
            module_levels={Module.MATERIAL: 2, Module.PROJECTS: 0},
            special_rights=frozenset({SpecialRight.PURCHASE_PRICES}),
        )
        self.assertIn("Buchhaltung", [str(link.label) for link in entries_for(rights)])
        self.assertNotIn("Buchhaltung", [str(link.label) for link in entries_for(rights, bookkeeping=False)])

    def test_the_tabs_follow_the_setting(self) -> None:
        rights = Rights.everything()
        on = outgoing_tabs.tabs(rights)
        self.assertTrue(
            all(on[key] for key in ("may_see_incoming", "may_see_open_items", "may_see_euer", "may_see_bank"))
        )
        settings = SystemSettings.load()
        settings.invoices_enabled = False
        settings.save()
        off = outgoing_tabs.tabs(rights)
        self.assertTrue(off["may_see_outgoing"] and off["may_use_statements"])
        for key in (
            "may_see_incoming",
            "may_capture",
            "may_see_assets",
            "may_use_legacy",
            "may_see_open_items",
            "may_see_euer",
            "may_see_bank",
        ):
            self.assertFalse(off[key], key)
