# SPDX-License-Identifier: GPL-3.0-or-later
"""Review round 4: the cost of the stock watch, one text for the overall discount (R4-1, R4-6).

Each test names the finding it guards. (The hostile-input and API tests of this round are in ``tests/api``.)
"""

from __future__ import annotations

import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from rentalars.accounts.models import User
from rentalars.core.models import AuditLogEntry
from rentalars.documents import services as document_services
from rentalars.documents.content import build_priced
from rentalars.documents.pdf import render_html
from rentalars.projects import services
from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_html
from rentalars.projects.stock_watch import stock_stamp, watched_models
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_line, make_product, make_project, ready_for_invoices
from tests.ui.base import UiTestCase


class StockStampCostTests(RentalarsTestCase):
    """(stock watch; R4-1) "The newest entry of a kind" must be answered from an index."""

    def test_the_change_log_has_an_index_on_kind_and_id(self) -> None:
        constraints = connection.introspection.get_constraints(connection.cursor(), AuditLogEntry._meta.db_table)
        columns = [tuple(info["columns"]) for info in constraints.values() if info["index"]]
        self.assertIn(("content_type_id", "id"), columns)

    def test_the_stamp_is_one_cheap_query_per_kind_and_keeps_its_form(self) -> None:
        project = make_project("Stempel", rental_days=1)
        add_line(project, make_product("S-401", price="10.00"), 1)
        user = User.objects.create_superuser("stamper", "s@example.org", "pw")
        first = stock_stamp(project.pk, user)  # warms the content types and rights
        with CaptureQueriesContext(connection) as queries:
            again = stock_stamp(project.pk, user)
        self.assertEqual(again, first)
        parts = first.split("-")
        self.assertEqual(len(parts), len(watched_models()))
        self.assertTrue(all(part.isdigit() for part in parts))
        newest = [q["sql"] for q in queries.captured_queries if "core_auditlogentry" in q["sql"]]
        self.assertEqual(len(newest), len(watched_models()))
        # Nothing reads rows or sorts: one MAX over the index per kind.
        self.assertTrue(all("MAX(" in sql and "ORDER BY" not in sql for sql in newest), newest)


class PrintedPercentEverywhereTests(UiTestCase):
    """(R4-6) The planning page, the price overview, the CSV and the documents print the same text."""

    def project_with(self, percent: str, article: str) -> object:
        project = make_project("P", rental_days=1, customer=ready_for_invoices())
        add_line(project, make_product(article, price="12345.67", billing_mode="flat"), 1)
        services.set_overall_discount(project, rights=ALL_RIGHTS, percent=percent)
        return project

    def test_every_place_prints_the_same_percentage(self) -> None:
        cases = {"19.99994": "19,99994", "10": "10", "12.5": "12,5", "0.123456": "0,123456", "33.333333": "33,333333"}
        for number, (percent, printed) in enumerate(cases.items()):
            project = self.project_with(percent, f"L-93{number}")
            wanted = f"Gesamtrabatt {printed} %"
            content = build_priced(project, "offer", title="A", number="1", issued_on=datetime.date(2027, 3, 1))
            with self.subTest(percent=percent):
                planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
                overview = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[project.pk])))
                with translation.override("de"):
                    csv = render_price_overview_csv(project)
                    overview_pdf = render_price_overview_html(project)
                    document = render_html(content, document_services.template_for("offer"))
                    title = next(section.title for section in content.sections if section.overall_discount)
                self.assertEqual(title, wanted)
                for name, text in (
                    ("planning page", planning),
                    ("price overview", overview),
                    ("price overview CSV", csv),
                    ("price overview PDF", overview_pdf),
                    ("document PDF", document),
                ):
                    self.assertIn(wanted, " ".join(text.split()), name)
