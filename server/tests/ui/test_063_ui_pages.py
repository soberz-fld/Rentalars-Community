# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages: filters that fold away (UIX-030), the credit (UIX-031), the company in the menu (UIX-032) and the
pages without login in one centred column (fix)."""

from __future__ import annotations

import re

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars import CREDIT_NAME, CREDIT_URL
from rentalars.api import webhooks
from rentalars.core.models import CompanyProfile
from tests.ui.base import UiTestCase, form_data

#: UIX-030: the lists with folding filters: address, key of the panel, whether a search field stays in front.
LISTS = (
    ("projects:list", "projects", True),
    ("material:item_list", "material-items", True),
    ("material:model_list", "material-models", True),
    ("material:inspections", "inspections", False),
    ("products:list", "products", True),
    ("customers:list", "customers", True),
    ("customers:venue_list", "venues", True),
    ("personnel:person_list", "people", True),
    ("timetracking:approval", "time-approval", False),
    ("timetracking:report", "time-report", False),
    ("availability:shortages", "shortages", False),
    ("mail:log", "mail-log", True),
    ("core:audit_log", "audit-log", True),
    ("core:access_log", "access-log", True),
    ("accounts:security_log", "security-log", True),
)


class FoldingFilterTests(UiTestCase):
    """UIX-030: one pattern on every list – search in front, the button, the other filters behind it."""

    def filter_form(self, page: str) -> str:
        match = re.search(r'<form method="get" class="filters[^"]*"[^>]*>(.*?)</form>', page, re.S)
        self.assertIsNotNone(match)
        return match.group(1)

    def assert_folding(self, page: str, key: str, with_search: bool) -> None:
        form = self.filter_form(page)
        toggle = re.search(r"<button [^>]*data-filter-toggle=\"" + key + r"\"[^>]*>", form)
        self.assertIsNotNone(toggle, key)
        self.assertIn('type="button"', toggle.group(0))
        self.assertIn(f'aria-controls="filter-panel-{key}"', toggle.group(0))
        self.assertIn(f'aria-describedby="filter-summary-{key}"', toggle.group(0))
        # The state is the script's to set: without it, nothing claims to be folded.
        self.assertNotIn("aria-expanded", toggle.group(0))
        self.assertIn(f'<span class="filter-summary" id="filter-summary-{key}" data-filter-summary hidden>', form)
        panel_start = form.index(f'id="filter-panel-{key}"')
        if with_search:
            self.assertLess(form.index('id="f-q"'), form.index("data-filter-toggle"))
            self.assertNotIn('id="f-q"', form[panel_start:])
        # Every field that filters, and the button that applies them, are behind the button.
        before = form[:panel_start]
        self.assertEqual(re.findall(r"<select ", before), [], key)
        self.assertNotIn('type="submit"', before)
        self.assertIn("<select" if "<select" in form else "<input", form[panel_start:])

    def test_every_list(self) -> None:
        for name, key, with_search in LISTS:
            with self.subTest(list=name):
                page = self.assert_ok(self.client.get(reverse(name)))
                self.assert_folding(page, key, with_search)
                self.assertIn("Filter</span>", page)

    def test_the_deliveries_of_a_webhook(self) -> None:
        webhook, _secret = webhooks.create_webhook(
            url="https://erp.example.de/hook", events=["project.created"], is_active=True, description="ERP"
        )
        page = self.assert_ok(self.client.get(reverse("webhooks:detail", args=[webhook.pk])))
        self.assert_folding(page, "webhook-deliveries", False)

    def test_the_default_number_of_days_of_the_inspections_is_named(self) -> None:
        from rentalars.material.inspections import SOON_DAYS

        page = self.assert_ok(self.client.get(reverse("material:inspections")))
        self.assertIn(f'value="{SOON_DAYS}" data-filter-default="{SOON_DAYS}"', page)

    def test_filters_still_work(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list"), {"status": "confirmed", "q": "x"}))
        self.assertIn('<option value="confirmed" selected>', page)
        self.assertIn('id="f-q" name="q" value="x"', page)


class CreditTests(UiTestCase):
    """UIX-031: "von fld-vt.de" below the version, in the menu and below the login."""

    def assert_credit(self, page: str) -> None:
        self.assertIn(
            f'<span class="credit">von <a href="{CREDIT_URL}" target="_blank" rel="noopener">{CREDIT_NAME}</a></span>',
            page,
        )

    def test_in_the_menu_below_the_version(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:home")))
        self.assert_credit(page)
        self.assertLess(page.index('<div class="version">'), page.index('<div class="credit-line">'))
        self.assertEqual((CREDIT_NAME, CREDIT_URL), ("fld-vt.de", "https://fld-vt.de"))

    def test_below_the_login(self) -> None:
        self.client.logout()
        page = self.assert_ok(self.client.get(reverse("accounts:login")))
        self.assertIn('<p class="public-foot">Rentalars ', page)
        self.assert_credit(page)

    def test_licence_is_unchanged(self) -> None:
        from django.conf import settings

        licence = (settings.BASE_DIR / "LICENSE").read_text(encoding="utf-8")
        self.assertNotIn(CREDIT_NAME, licence)


class CompanyInTheMenuTests(UiTestCase):
    """UIX-032: the company name under the name of the application, without a query per page."""

    def name_company(self, name: str) -> None:
        company = CompanyProfile.load()
        company.name = name
        company.save()

    def test_shown_under_the_name_in_the_menu_and_the_top_bar(self) -> None:
        self.name_company("Lichtwerk & Ton GmbH")
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertEqual(page.count('<span class="brand-company">Lichtwerk &amp; Ton GmbH</span>'), 2)
        self.assertIn('<p class="sidebar-company">Lichtwerk &amp; Ton GmbH</p>', page)

    def test_nothing_without_a_name(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertNotIn("brand-company", page)
        self.assertNotIn("sidebar-company", page)
        self.assertIn('<span class="brand-name">Rentalars</span>', page)

    def test_no_query_per_page_and_a_new_name_at_once(self) -> None:
        self.client.get(reverse("projects:list"))
        with CaptureQueriesContext(connection) as without_name:
            self.assert_ok(self.client.get(reverse("projects:list")))
        self.name_company("Lichtwerk GmbH")
        with CaptureQueriesContext(connection) as queries:
            page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn("Lichtwerk GmbH", page)
        self.assertEqual(len(queries), len(without_name))
        # The name comes with the user of the session, in the same query.
        own = [query["sql"] for query in queries if "core_companyprofile" in query["sql"]]
        self.assertEqual(len(own), 1)
        # Quoted with " on SQLite and with ` on MariaDB.
        self.assertRegex(own[0], r"FROM [\"`]accounts_user[\"`]")

        url = reverse("core:company_settings")
        data = form_data(self.client.get(url), containing="company-name")
        data.update({"form": "company", "company-name": "Tonwerk GmbH"})
        self.assertRedirects(self.client.post(url, data), url)
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn('<span class="brand-company">Tonwerk GmbH</span>', page)
        self.assertNotIn("Lichtwerk", page)

    def test_not_on_the_pages_without_login(self) -> None:
        self.name_company("Lichtwerk GmbH")
        self.client.logout()
        page = self.assert_ok(self.client.get(reverse("accounts:login")))
        self.assertNotIn("Lichtwerk", page)


class PublicPagesTests(UiTestCase):
    """Fix: logo, box and footer of the pages without login in one column (centred by app.css)."""

    def test_one_column(self) -> None:
        self.client.logout()
        for name in ("accounts:login", "accounts:password_reset"):
            with self.subTest(page=name):
                page = self.assert_ok(self.client.get(reverse(name)))
                column = page.index('<div class="public-column">')
                self.assertLess(column, page.index('<div class="public-brand">'))
                self.assertLess(page.index('<div class="public-card'), page.index('<p class="public-foot">'))
