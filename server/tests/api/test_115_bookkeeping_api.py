# SPDX-License-Identifier: GPL-3.0-or-later
"""API: without "use Rentalars as accounting software" the API of bookkeeping answers 400 (DOK-055)."""

from __future__ import annotations

from rentalars.core.models import SystemSettings
from rentalars.documents import bookkeeping
from tests.api.base import API, ApiTestCase

BOOKKEEPING = (
    "/incoming-invoices",
    "/incoming-invoices/totals",
    "/incoming-settings",
    "/accounting/open-items",
    "/accounting/bank/imports",
    "/accounting/euer",
    "/accounting/archive",
    "/asset-register",
    "/stock-sales",
    "/legacy-imports",
)
STAYING = ("/accounting/documents", "/accounting/settings", "/settings", "/projects")


class BookkeepingApiTests(ApiTestCase):
    def switch(self, on: bool) -> None:
        settings = SystemSettings.load()
        settings.invoices_enabled = on
        settings.save()

    def test_on_the_calls_answer_as_before(self) -> None:
        for path in BOOKKEEPING:
            self.assertEqual(self.admin.get(f"{API}{path}").status_code, 200, path)

    def test_off_they_are_refused_clearly(self) -> None:
        self.switch(False)
        for path in BOOKKEEPING:
            error = self.assert_error(self.admin.get(f"{API}{path}"), 400, "accounting_disabled")
            self.assertIn("Buchhaltungsprogramm", error["message"], path)

    def test_off_a_change_is_refused_too(self) -> None:
        self.switch(False)
        self.assert_error(
            self.admin.post(f"{API}/accounting/archive/verify", {}, format="json"), 400, "accounting_disabled"
        )

    def test_off_the_rest_works(self) -> None:
        self.switch(False)
        for path in STAYING:
            self.assertEqual(self.admin.get(f"{API}{path}").status_code, 200, path)

    def test_the_switch_itself_can_be_turned_on_again_through_the_api(self) -> None:
        self.switch(False)
        response = self.admin.patch(f"{API}/settings", {"system": {"invoices_enabled": True}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.admin.get(f"{API}/incoming-invoices").status_code, 200)

    def test_without_login_the_answer_is_401_not_a_hint_on_the_setting(self) -> None:
        from rest_framework.test import APIClient

        self.switch(False)
        self.assertEqual(APIClient().get(f"{API}/incoming-invoices").status_code, 401)

    def test_a_made_up_token_gets_401_not_a_hint_on_the_setting(self) -> None:
        from rest_framework.test import APIClient

        self.switch(False)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        self.assertEqual(client.get(f"{API}/incoming-invoices").status_code, 401)

    def test_off_every_address_of_the_list_is_refused(self) -> None:
        """DOK-055: the whole list, not only a sample – whatever the method or the address parameters."""
        import re

        from tests.unit.test_115_bookkeeping import page_names

        self.switch(False)
        checked = 0
        for name, route in page_names().items():
            if not name.startswith("api:") or not bookkeeping.is_bookkeeping(name):
                continue
            path = "/" + re.sub(r"<[^>]+>", "1", route).lstrip("/")
            checked += 1
            self.assert_error(self.admin.get(path), 400, "accounting_disabled")
        self.assertGreater(checked, 30)
