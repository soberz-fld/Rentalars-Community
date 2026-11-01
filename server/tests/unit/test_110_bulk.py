# SPDX-License-Identifier: GPL-3.0-or-later
"""Ticked rows in every table and the download of the chosen rows as CSV (``core.bulk``).

The requirement: tick boxes for bulk actions in all table views, as for the items; for a table without a sensible change the decision is a CSV download – every table at least "download the selection as CSV".
"""

from __future__ import annotations

from django.test import RequestFactory
from django.urls import reverse

from rentalars.core.tables import REGISTRY
from rentalars.customers.tables import CUSTOMER_TABLE
from tests.helpers import make_customer
from tests.ui.base import UiTestCase


class SelectionTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.alpha = make_customer("Alpha Bühnenbau")
        self.beta = make_customer("Beta Veranstaltungen")
        self.gamma = make_customer("Gamma Messe")
        self.name = f"sel_{CUSTOMER_TABLE.key}"

    def post(self, ids: list[int], **extra: str):
        data = {
            "table": CUSTOMER_TABLE.key,
            "prefix": CUSTOMER_TABLE.prefix,
            "next": reverse("customers:list") + "?q=",
            self.name: [str(pk) for pk in ids],
            **extra,
        }
        return self.client.post(reverse("core:bulk_csv"), data)

    def test_the_list_has_tick_boxes_and_the_bar(self) -> None:
        page = self.assert_ok(self.client.get(reverse("customers:list")))
        self.assertIn(f'name="{self.name}" value="{self.beta.pk}"', page)
        self.assertIn(f'data-bulk-bar="{self.name}"', page)
        self.assertIn(f'data-check-all="{self.name}"', page)
        self.assertIn("Auswahl als CSV herunterladen", page)
        self.assertEqual(page.count(f'id="bulk-{CUSTOMER_TABLE.key}"'), 1)

    def test_the_chosen_rows_come_as_csv_made_by_the_list_itself(self) -> None:
        response = self.post([self.alpha.pk, self.gamma.pk])
        self.assertEqual(response.status_code, 302)
        self.assertIn("format=csv", response["Location"])
        self.assertIn(f"only={self.alpha.pk}%2C{self.gamma.pk}", response["Location"])
        csv = self.client.get(response["Location"])
        self.assertEqual(csv.status_code, 200)
        text = csv.content.decode("utf-8")
        self.assertIn("Alpha Bühnenbau", text)
        self.assertIn("Gamma Messe", text)
        self.assertNotIn("Beta Veranstaltungen", text)
        # Without the choice the whole list comes, as before.
        everything = self.client.get(reverse("customers:list"), {"format": "csv"}).content.decode("utf-8")
        self.assertIn("Beta Veranstaltungen", everything)

    def test_nothing_chosen_goes_back_with_a_hint(self) -> None:
        response = self.post([])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("customers:list") + "?q=")
        self.assertTrue(
            any("mindestens eine Zeile" in text for text in self.messages_of(self.client.get(response["Location"])))
        )

    def test_page_and_old_choices_are_dropped_from_the_address(self) -> None:
        response = self.post([self.beta.pk], next=reverse("customers:list") + "?q=a&page=3&only=9")
        self.assertIn("q=a", response["Location"])
        self.assertNotIn("page=3", response["Location"])
        self.assertIn(f"only={self.beta.pk}", response["Location"])
        self.assertNotIn("only=9", response["Location"])

    def test_unknown_tables_and_foreign_addresses_are_refused(self) -> None:
        self.assertEqual(self.post([1], table="../x").status_code, 400)
        self.assertEqual(self.post([1], table="").status_code, 400)
        self.assertEqual(self.post([1], prefix="Other?").status_code, 400)
        response = self.post([self.alpha.pk], next="https://evil.example/steal")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/?"), response["Location"])  # our own start page, not theirs
        self.assertEqual(self.client.get(reverse("core:bulk_csv")).status_code, 405)

    def test_only_reads_numbers_and_few_of_them(self) -> None:
        factory = RequestFactory()

        def state(**params: str):
            request = factory.get("/customers/", params)
            request.user = self.admin_user
            return CUSTOMER_TABLE.state(request)

        self.assertEqual(state(only="3, 4,x,5;6,99999999999999").selected_ids, {3, 4})
        self.assertIsNone(state().selected_ids)
        empty = state(only="")
        self.assertEqual(empty.selected_ids, set())

    def test_every_table_is_known_to_the_registry_with_a_plain_key(self) -> None:
        for key, definition in REGISTRY.items():
            self.assertRegex(key, r"^[a-z0-9_]+$")
            self.assertRegex(definition.prefix, r"^[a-z0-9_]*$")
