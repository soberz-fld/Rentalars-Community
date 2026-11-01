# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of handing invoices to the accounting: DOK-011 (Lexware Office) and DOK-012 (DATEV export)."""

from __future__ import annotations

from rentalars.documents import services
from rentalars.documents.models import AccountingSettings, DocumentKind
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, make_product, make_project, ready_for_invoices
from tests.lexware_fake import TAX_FREE_EU, FakeLexware

KEY = "lexware-test-key-0123456789abcdef"


class AccountingApiCase(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.customer = ready_for_invoices()
        self.project = make_project("Stadtfest", customer=self.customer)
        add_line(self.project, make_product("L-010", "Lichtpauschale", price="100.00", billing_mode="flat"), 2)
        self.invoice = services.create_document(self.project, DocumentKind.INVOICE)


class AccountingSettingsApiTests(AccountingApiCase):
    def test_settings_are_read_and_changed_but_the_key_is_never_returned(self) -> None:
        body = self.admin.get(f"{API}/accounting/settings").json()
        self.assertEqual((body["lexware_enabled"], body["lexware_api_key_set"]), (False, False))
        self.assertNotIn("lexware_api_key", body)
        self.assertEqual(body["datev_effective_revenue_accounts"], {"19": "8400", "7": "8300", "0": "8336"})

        refused = self.admin.patch(f"{API}/accounting/settings", {"lexware_enabled": True}, format="json")
        self.assert_error(refused, 400, "validation_error", "lexware_enabled")
        wrong = self.admin.patch(f"{API}/accounting/settings", {"datev_revenue_accounts": {"19": "84"}}, format="json")
        self.assert_error(wrong, 400, "validation_error", "datev_revenue_accounts")

        changed = self.admin.patch(
            f"{API}/accounting/settings",
            {
                "lexware_enabled": True,
                "lexware_api_key": KEY,
                "lexware_categories": {"0": TAX_FREE_EU},
                "datev_consultant_number": 29098,
                "datev_client_number": 55003,
                "datev_chart": "SKR04",
                "datev_revenue_accounts": {"19": "4401"},
            },
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertNotIn(KEY, changed.content.decode())
        body = changed.json()
        self.assertEqual(
            (body["lexware_enabled"], body["lexware_api_key_set"], body["lexware_api_key_hint"]), (True, True, "…cdef")
        )
        self.assertEqual(body["datev_effective_revenue_accounts"], {"19": "4401", "7": "4300", "0": "4336"})
        self.assertEqual(AccountingSettings.objects.get().lexware_api_key, KEY)
        # Without a new key, the key stays.
        self.admin.patch(f"{API}/accounting/settings", {"lexware_automatic": True}, format="json")
        self.assertEqual(AccountingSettings.objects.get().lexware_api_key, KEY)

    def test_only_with_the_settings_and_the_price_right(self) -> None:
        for username, role in (("paula", "Projektleitung"), ("nora", "Nur-Lesen"), ("luka", "Lager")):
            client = self.client_for(username, role)
            self.assertEqual(client.get(f"{API}/accounting/settings").status_code, 403, role)
            self.assertEqual(
                client.get(f"{API}/accounting/datev/bookings?from=2027-03-01&to=2027-03-31").status_code, 403, role
            )
        reader = self.client_of(self.admin_user, read_only=True)
        self.assertEqual(reader.get(f"{API}/accounting/settings").status_code, 200)
        self.assertEqual(reader.patch(f"{API}/accounting/settings", {}, format="json").status_code, 403)

    def test_check_the_connection(self) -> None:
        with FakeLexware() as server:
            server.switch_on()
            checked = self.admin.post(f"{API}/accounting/lexware/check")
            self.assertEqual(checked.status_code, 200, checked.content)
            self.assertEqual(checked.json()["organization"], "Licht & Ton GmbH")
            self.assertEqual(len(checked.json()["categories"]), 3)
            server.fail(401)
            refused = self.admin.post(f"{API}/accounting/lexware/check")
        error = self.assert_error(refused, 400, "validation_error")
        self.assertIn("API-Schlüssel abgelehnt", error["message"])


class LexwareTransferApiTests(AccountingApiCase):
    def test_hand_over_a_document_and_read_its_state(self) -> None:
        address = f"{API}/documents/{self.invoice.pk}/lexware"
        self.assertEqual(self.admin.get(address).json()["transfer_state"], "none")
        with FakeLexware() as server:
            server.switch_on(collective=True)
            started = self.admin.post(address, {}, format="json")
            self.assertEqual(started.status_code, 202, started.content)
            twice = self.admin.post(address, {}, format="json")
        self.assertEqual(started.json()["transfer_state"], "done")
        state = self.admin.get(address).json()
        self.assertEqual(
            (state["number"], state["transfer_state"], state["pdf_uploaded"], state["voucher_id"] in server.vouchers),
            ("RE-2027-0001", "done", True, True),
        )
        self.assertIn(
            "RE-2027-0001 ist schon in Lexware Office.", self.assert_error(twice, 400, "validation_error")["message"]
        )

    def test_who_may_hand_over(self) -> None:
        address = f"{API}/documents/{self.invoice.pk}/lexware"
        FakeLexware.switch_on(collective=True)
        self.assertEqual(self.client_for("luka", "Lager").post(address, {}, format="json").status_code, 403)
        self.assertEqual(self.client_for("nora", "Nur-Lesen").get(address).status_code, 200)
        self.assertEqual(self.client_for("otto", "Nur-Lesen").post(address, {}, format="json").status_code, 403)
        with FakeLexware():
            started = self.client_for("paula", "Projektleitung").post(address, {"new_contact": False}, format="json")
        self.assertEqual(started.status_code, 202)

    def test_the_list_of_handings_over(self) -> None:
        cancellation = services.cancel_invoice(self.invoice)
        with FakeLexware() as server:
            server.switch_on()
            server.add_contact(int(self.customer.number), company="Ganz andere GmbH")
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                self.admin.post(f"{API}/documents/{self.invoice.pk}/lexware", {}, format="json")
            self.admin.post(f"{API}/documents/{cancellation.pk}/lexware", {"new_contact": True}, format="json")
        failed = self.admin.get(f"{API}/accounting/lexware/transfers").json()
        self.assertEqual([(t["number"], t["transfer_state"], t["error_code"]) for t in failed],
                         [("RE-2027-0001", "failed", "contact_conflict")])  # fmt: skip
        done = self.admin.get(f"{API}/accounting/lexware/transfers?state=done").json()
        self.assertEqual([t["number"] for t in done], ["RE-2027-0002"])
        self.assert_error(self.admin.get(f"{API}/accounting/lexware/transfers?state=nonsense"), 400, "validation_error")


class DatevApiTests(AccountingApiCase):
    def test_bookings_and_debitors_of_a_period(self) -> None:
        missing = self.admin.get(f"{API}/accounting/datev/bookings?from=2027-03-01&to=2027-03-31")
        self.assertIn("Beraternummer", self.assert_error(missing, 400, "validation_error")["message"])
        self.admin.patch(
            f"{API}/accounting/settings",
            {"datev_consultant_number": 29098, "datev_client_number": 55003},
            format="json",
        )
        bookings = self.admin.get(f"{API}/accounting/datev/bookings?from=2027-03-01&to=2027-03-31")
        self.assertEqual(bookings.status_code, 200, bookings.content)
        self.assertEqual(bookings["Content-Type"], "text/csv; charset=windows-1252")
        lines = bookings.content.decode("cp1252").split("\r\n")
        self.assertTrue(lines[0].startswith('"EXTF";700;21;"Buchungsstapel";13;'))
        self.assertTrue(lines[2].startswith(f'238,00;"S";"EUR";;;;{self.customer.number};8400;"";0103;"RE-2027-0001"'))
        debitors = self.admin.get(f"{API}/accounting/datev/debitors?from=2027-03-01&to=2027-03-31")
        self.assertEqual(debitors.status_code, 200, debitors.content)
        self.assertIn('attachment; filename="EXTF_Debitoren_20270301_20270331.csv"', debitors["Content-Disposition"])
        self.assertTrue(
            debitors.content.decode("cp1252").split("\r\n")[2].startswith(f'{self.customer.number};"Stadtwerke')
        )
        wrong = self.admin.get(f"{API}/accounting/datev/bookings?from=2027-03-01&to=31.03.2027")
        self.assert_error(wrong, 400, "validation_error", "to")
        reversed_period = self.admin.get(f"{API}/accounting/datev/debitors?from=2027-03-31&to=2027-03-01")
        self.assertIn("endet, bevor er beginnt", self.assert_error(reversed_period, 400, "validation_error")["message"])
