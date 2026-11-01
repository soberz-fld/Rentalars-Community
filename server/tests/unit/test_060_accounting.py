# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of handing invoices to the accounting: DOK-011 (Lexware Office) and DOK-012 (DATEV export)."""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError

from rentalars.core.crypto import decrypt_secret
from rentalars.core.models import AuditLogEntry
from rentalars.customers.models import Customer, CustomerKind
from rentalars.documents import datev, lexware, services
from rentalars.documents.content import from_json
from rentalars.documents.models import (
    AccountingSettings,
    ChartOfAccounts,
    DebitorMode,
    DocumentKind,
    LexwareTransfer,
    TransferState,
    rate_key,
)
from rentalars.documents.xrechnung import NAMESPACES
from rentalars.masterdata.models import TaxRate
from rentalars.notifications.models import Notification
from tests.helpers import RentalarsTestCase, add_line, at, make_customer, make_product, make_project, make_user
from tests.helpers import ready_for_invoices as prepare
from tests.lexware_fake import INCOME, TAX_FREE_EU, FakeLexware, voucher_problems


class AccountingCase(RentalarsTestCase):
    """A project with 200,00 at 19 % and 50,00 at 7 %: an invoice of 291,50."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = prepare()
        self.seven = TaxRate.objects.create(name="7 %", rate=Decimal("7.00"))
        self.project = make_project("Stadtfest", customer=self.customer, start=at(10, 8), end=at(12, 18))
        add_line(self.project, make_product("L-010", "Lichtpauschale", price="100.00", billing_mode="flat"), 2)
        add_line(
            self.project,
            make_product("L-020", "Programmheft", price="10.00", billing_mode="flat", tax_rate=self.seven),
            5,
        )
        self.user = make_user("luka")

    def invoice(self, project: object = None) -> object:
        return services.create_document(project or self.project, DocumentKind.INVOICE, user=self.user)


class VoucherTests(AccountingCase):
    """DOK-011: the voucher and the contact as Lexware Office documents them."""

    def test_an_invoice_becomes_a_sales_voucher_with_the_amounts_of_its_tax_rates(self) -> None:
        invoice = self.invoice()
        content = from_json(invoice.content)
        body = lexware.voucher_body(
            invoice, content, AccountingSettings.load(), contact_id="c0ffee00-0000-4000-8000-000000000001"
        )
        self.assertEqual(
            body,
            {
                "type": "salesinvoice",
                "voucherNumber": "RE-2027-0001",
                "voucherDate": "2027-03-01",
                "shippingDate": "2027-03-12",
                "dueDate": "2027-03-15",
                "totalGrossAmount": 291.5,
                "totalTaxAmount": 41.5,
                "taxType": "net",
                "useCollectiveContact": False,
                "contactId": "c0ffee00-0000-4000-8000-000000000001",
                "remark": "Projekt 2027-0001 „Stadtfest“ – Rentalars",  # ADM-014: the number without "P-" again
                "voucherItems": [
                    {"amount": 200.0, "taxAmount": 38.0, "taxRatePercent": 19, "categoryId": INCOME},
                    {"amount": 50.0, "taxAmount": 3.5, "taxRatePercent": 7, "categoryId": INCOME},
                ],
            },
        )
        # The amounts per tax rate are those of the XRechnung, to the cent.
        root = ET.fromstring(invoice.xml_file.read())
        cac, cbc = "{" + NAMESPACES["cac"] + "}", "{" + NAMESPACES["cbc"] + "}"
        subtotals = [
            (float(sub.find(f"{cbc}TaxableAmount").text), float(sub.find(f"{cbc}TaxAmount").text))
            for sub in root.iter(f"{cac}TaxSubtotal")
        ]
        self.assertEqual(subtotals, [(item["amount"], item["taxAmount"]) for item in body["voucherItems"]])
        self.assertEqual(voucher_problems(body, {"c0ffee00-0000-4000-8000-000000000001": {}}), [])

    def test_a_cancellation_becomes_a_credit_note_with_positive_amounts(self) -> None:
        cancellation = services.cancel_invoice(self.invoice())
        accounting = AccountingSettings.load()
        accounting.lexware_categories = {"7": TAX_FREE_EU}
        body = lexware.voucher_body(cancellation, from_json(cancellation.content), accounting, contact_id="")
        self.assertEqual(
            (body["type"], body["voucherNumber"], body["totalGrossAmount"], body["useCollectiveContact"]),
            ("salescreditnote", "RE-2027-0002", 291.5, True),
        )
        self.assertNotIn("contactId", body)
        self.assertNotIn("dueDate", body)
        self.assertEqual([item["amount"] for item in body["voucherItems"]], [200.0, 50.0])
        self.assertEqual([item["categoryId"] for item in body["voucherItems"]], [INCOME, TAX_FREE_EU])
        self.assertIn("Storniert Rechnung RE-2027-0001", body["remark"])
        self.assertEqual(voucher_problems(body, {}), [])

    def test_a_contact_for_a_company_and_for_a_private_person(self) -> None:
        self.customer.vat_id, self.customer.tax_number, self.customer.country = (
            "ATU12345678",
            "12/345/67890",
            "Österreich",
        )
        self.customer.save()
        self.customer.contacts.create(name="Paula Petersen", salutation="Frau", email="p@stadtwerke.example")
        body = lexware.contact_body(self.customer)
        self.assertEqual(
            body,
            {
                "version": 0,
                "roles": {"customer": {}},
                "company": {
                    "name": "Stadtwerke Musterstadt",
                    "taxNumber": "12/345/67890",
                    "vatRegistrationId": "ATU12345678",
                    "contactPersons": [
                        {
                            "firstName": "Paula",
                            "lastName": "Petersen",
                            "primary": True,
                            "salutation": "Frau",
                            "emailAddress": "p@stadtwerke.example",
                        }
                    ],
                },
                "addresses": {
                    "billing": [{"countryCode": "AT", "street": "Markt 1", "zip": "12345", "city": "Musterstadt"}]
                },
                "emailAddresses": {"business": ["a@b.example"]},
                "note": f"Von Rentalars angelegt für den Kunden {self.customer.number}.",
            },
        )
        private = Customer(number="10077", kind=CustomerKind.PRIVATE, name="Anna Maria Beispiel", phone="0170 1")
        body = lexware.contact_body(private)
        self.assertEqual(body["person"], {"firstName": "Anna Maria", "lastName": "Beispiel"})
        self.assertEqual((body["phoneNumbers"], "addresses" in body), ({"business": ["0170 1"]}, False))

    def test_names_count_as_the_same_customer_like_the_duplicate_check(self) -> None:
        self.assertTrue(lexware.same_name("Stadtwerke Musterstadt GmbH", "stadtwerke musterstadt"))
        self.assertTrue(lexware.same_name("Stadtwerke Musterstadt", "Stadtwerke Musterstadt Veranstaltungen"))
        self.assertFalse(lexware.same_name("Stadtwerke Musterstadt", "Stadthalle Musterstadt"))
        self.assertFalse(lexware.same_name("", "Stadtwerke"))


class TransferTests(AccountingCase):
    """DOK-011: handing over – contact, voucher, PDF; nothing twice; clear errors."""

    def test_the_customer_is_found_by_its_number_and_the_pdf_follows_the_voucher(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            contact_id = server.add_contact(int(self.customer.number), company="Stadtwerke Musterstadt GmbH")
            server.switch_on()
            transfer = lexware.request_transfer(invoice, user=self.user)
        self.assertEqual((transfer.state, transfer.contact_id, transfer.pdf_uploaded), ("done", contact_id, True))
        self.assertEqual(
            [(request.method, request.path) for request in server.requests],
            [
                ("GET", "/v1/voucherlist"),
                ("GET", "/v1/contacts"),
                ("POST", "/v1/vouchers"),
                ("POST", f"/v1/vouchers/{transfer.voucher_id}/files"),
            ],
        )
        self.assertEqual(server.requests[0].query["voucherNumber"], "RE-2027-0001")
        self.assertEqual(server.requests[1].query, {"number": self.customer.number, "customer": "true"})
        self.assertTrue(all(r.headers["Authorization"] == f"Bearer {server.api_key}" for r in server.requests))
        voucher = server.vouchers[transfer.voucher_id]
        self.assertEqual((voucher["contactId"], voucher["totalGrossAmount"]), (contact_id, 291.5))
        invoice.file.open("rb")
        self.assertEqual(server.files[transfer.voucher_id], [("Rechnung-RE-2027-0001.pdf", invoice.file.read())])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.lexware_contact_id, contact_id)
        # Two requests per second at most: Rentalars waited between them.
        self.assertEqual(len(server.waits), 3)
        self.assertTrue(all(0.4 < wait <= 0.5 for wait in server.waits))
        # Noted on the document and in the history of the project.
        self.assertEqual(lexware.transfer_of(invoice).transferred_at, transfer.transferred_at)
        self.assertTrue(AuditLogEntry.objects.filter(event="document.transferred").exists())

    def test_an_unknown_customer_is_created_and_then_known(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.switch_on()
            first = lexware.request_transfer(invoice, user=self.user)
            created = server.of("POST", "/v1/contacts")
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0].json["company"]["name"], "Stadtwerke Musterstadt")
            # The cancellation goes to the same contact without asking again.
            cancellation = services.cancel_invoice(invoice, user=self.user)
            second = lexware.request_transfer(cancellation, user=self.user)
        self.assertEqual((first.state, second.state), ("done", "done"))
        self.assertEqual(first.contact_id, second.contact_id)
        self.assertEqual(len(server.of("POST", "/v1/contacts")), 1)
        self.assertEqual(len(server.of("GET", "/v1/contacts")), 1)
        self.assertEqual(server.vouchers[second.voucher_id]["type"], "salescreditnote")

    def test_a_number_that_belongs_to_another_customer_stops_until_asked_for_a_new_contact(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.add_contact(int(self.customer.number), first="Otto", last="Normalverbraucher")
            server.switch_on()
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                transfer = lexware.request_transfer(invoice, user=self.user)
            self.assertEqual((transfer.state, transfer.error_code), ("failed", "contact_conflict"))
            self.assertIn(
                f"In Lexware Office gehört die Kundennummer {self.customer.number} zu „Otto Normalverbraucher“, "
                "in Rentalars zu „Stadtwerke Musterstadt“.",
                transfer.error,
            )
            self.assertEqual(server.vouchers, {})
            transfer = lexware.request_transfer(invoice, user=self.user, new_contact=True)
        self.assertEqual((transfer.state, transfer.attempts), ("done", 2))
        self.assertEqual(len(server.of("POST", "/v1/contacts")), 1)

    def test_the_collective_contact_needs_no_customer(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.switch_on(collective=True)
            transfer = lexware.request_transfer(invoice, user=self.user)
        self.assertEqual((transfer.state, transfer.contact_id), ("done", ""))
        self.assertTrue(server.vouchers[transfer.voucher_id]["useCollectiveContact"])
        self.assertEqual(server.of("GET", "/v1/contacts") + server.of("POST", "/v1/contacts"), [])

    def test_nothing_is_handed_over_twice(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.switch_on()
            lexware.request_transfer(invoice, user=self.user)
            with self.assertRaisesMessage(ValidationError, "RE-2027-0001 ist schon in Lexware Office."):
                lexware.request_transfer(invoice, user=self.user)
        self.assertEqual(len(server.vouchers), 1)

    def test_a_voucher_that_is_there_already_is_taken_and_only_the_pdf_added(self) -> None:
        """A crash after the voucher was created, before Rentalars noted it: the next attempt finds it."""
        invoice = self.invoice()
        with FakeLexware() as server:
            voucher_id = server.add_voucher("RE-2027-0001", "291.50")
            server.switch_on()
            transfer = lexware.request_transfer(invoice, user=self.user)
        self.assertEqual((transfer.state, transfer.voucher_id), ("done", voucher_id))
        self.assertEqual(server.of("POST", "/v1/vouchers"), [server.of("POST", f"/v1/vouchers/{voucher_id}")[0]])
        self.assertEqual(len(server.files[voucher_id]), 1)

    def test_a_voucher_with_the_same_number_but_another_amount_is_not_taken(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.add_voucher("RE-2027-0001", "99.00")
            server.switch_on()
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                transfer = lexware.request_transfer(invoice, user=self.user)
        self.assertEqual((transfer.state, transfer.error_code), ("failed", "voucher_conflict"))
        self.assertIn("über 99,00 statt 291,50", transfer.error)
        self.assertEqual(server.files, {})

    def test_after_a_failed_upload_only_the_pdf_is_sent_again(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.switch_on()
            server.add_contact(int(self.customer.number), company="Stadtwerke Musterstadt")
            original = server._route

            def broken_upload(method: str, path: str, *args: object) -> tuple[int, object]:
                if path.endswith("/files"):
                    return 503, {"status": 503}
                return original(method, path, *args)

            server._route = broken_upload  # type: ignore[method-assign]
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                failed = lexware.request_transfer(invoice, user=self.user)
            self.assertEqual((failed.state, failed.error_code, failed.pdf_uploaded), ("failed", "server", False))
            self.assertTrue(failed.voucher_id)
            self.assertEqual(
                failed.error, "Lexware Office hat mit Fehler 503 geantwortet. Versuche es später noch einmal."
            )
            server._route = original  # type: ignore[method-assign]
            done = lexware.request_transfer(invoice, user=self.user)
        self.assertEqual((done.state, done.voucher_id, done.pdf_uploaded), ("done", failed.voucher_id, True))
        self.assertEqual(len(server.of("POST", "/v1/vouchers")) - len(server.of("POST", "/v1/vouchers/")), 1)

    def test_errors_are_named_in_german(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.switch_on(collective=True)
            server.fail(401)
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                transfer = lexware.request_transfer(invoice, user=self.user)
            self.assertEqual(transfer.error_code, "auth")
            self.assertEqual(
                transfer.error,
                "Lexware Office hat den API-Schlüssel abgelehnt. Prüfe ihn unter Einstellungen → Buchhaltung.",
            )
            server.fail(400, {"IssueList": [{"i18nKey": "invalid_value", "source": "voucherItems[0].categoryId"}]})
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                transfer = lexware.request_transfer(invoice, user=self.user)
            self.assertEqual(
                transfer.error,
                "Lexware Office hat die Daten abgelehnt: voucherItems[0].categoryId: invalid_value",
            )
            server.fail(
                406, {"message": "Validation failed", "details": [{"field": "voucherDate", "message": "zu alt"}]}
            )
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                transfer = lexware.request_transfer(invoice, user=self.user)
            self.assertEqual(transfer.error, "Lexware Office hat die Daten abgelehnt: voucherDate: zu alt")
            self.assertEqual((transfer.error_code, transfer.attempts), ("rejected", 3))

    def test_too_many_requests_are_asked_again_after_a_pause(self) -> None:
        invoice = self.invoice()
        with FakeLexware() as server:
            server.switch_on(collective=True)
            server.fail(429, times=2)
            transfer = lexware.request_transfer(invoice, user=self.user)
            self.assertEqual(transfer.state, "done")
            self.assertIn(1.0, server.waits)
            self.assertIn(2.0, server.waits)
            client = lexware.LexwareClient(server.api_key)
            server.fail(429, times=4)
            with self.assertRaises(lexware.LexwareError) as caught:
                client.profile()
        self.assertEqual(caught.exception.code, "rate_limit")
        self.assertIn("höchstens zwei Anfragen je Sekunde", str(caught.exception))

    def test_lexware_office_cannot_be_reached(self) -> None:
        def unreachable(*args: object, **kwargs: object) -> None:
            raise lexware.LexwareError(lexware._network_problem(TimeoutError()), code="unreachable")

        with (
            mock.patch("rentalars.documents.lexware._send", unreachable),
            self.assertRaises(lexware.LexwareError) as caught,
        ):
            lexware.LexwareClient("key").profile()
        self.assertEqual(caught.exception.code, "unreachable")
        self.assertEqual(
            str(caught.exception), "Lexware Office ist nicht erreichbar: keine Antwort innerhalb von 20 Sekunden."
        )

    def test_an_invoice_goes_over_at_once_when_set_so(self) -> None:
        with FakeLexware() as server:
            server.switch_on(automatic=True, collective=True)
            invoice = self.invoice()
            cancellation = services.cancel_invoice(invoice, user=self.user)
        self.assertEqual(
            [lexware.transfer_of(document).state for document in (invoice, cancellation)], ["done", "done"]
        )
        self.assertEqual(sorted(voucher["voucherNumber"] for voucher in server.vouchers.values()),
                         ["RE-2027-0001", "RE-2027-0002"])  # fmt: skip
        # Done without being asked for: no message.
        self.assertFalse(Notification.objects.filter(user=self.user).exists())

    def test_a_failed_automatic_handing_over_tells_who_made_the_invoice(self) -> None:
        with FakeLexware() as server:
            server.switch_on(automatic=True, collective=True)
            server.fail(500)
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                invoice = self.invoice()
        self.assertEqual(invoice.number, "RE-2027-0001")
        self.assertEqual(lexware.transfer_of(invoice).state, "failed")
        message = Notification.objects.get(user=self.user)
        self.assertEqual(message.title, "Nicht an Lexware Office übergeben: Rechnung RE-2027-0001")
        self.assertIn("Fehler 500", message.body)

    def test_handing_over_needs_the_settings_and_an_invoice(self) -> None:
        offer = services.create_document(self.project, DocumentKind.OFFER)
        with self.assertRaisesMessage(ValidationError, "ist ausgeschaltet"):
            lexware.request_transfer(self.invoice())
        FakeLexware.switch_on()
        with self.assertRaisesMessage(ValidationError, "Nur Rechnungen und Stornorechnungen"):
            lexware.request_transfer(offer)
        self.assertFalse(LexwareTransfer.objects.exists())

    def test_a_handing_over_on_the_way_is_not_started_twice(self) -> None:
        invoice = self.invoice()
        FakeLexware.switch_on()
        LexwareTransfer.objects.create(document=invoice, state=TransferState.RUNNING)
        with self.assertRaisesMessage(ValidationError, "wird schon an Lexware Office übergeben"):
            lexware.request_transfer(invoice)
        # Running for longer than 15 minutes: lost with a restart, it may be started again.
        LexwareTransfer.objects.update(updated_at=at(1) - lexware.STALE_AFTER * 2)
        with FakeLexware() as server:
            server.switch_on(collective=True)
            self.assertEqual(lexware.request_transfer(invoice).state, "done")


class SettingsTests(AccountingCase):
    def test_the_key_is_stored_encrypted_and_left_out_of_the_full_export(self) -> None:
        from rentalars.core import export

        accounting = AccountingSettings.load()
        accounting.set_lexware_api_key(" abc-123-key-4567 ")
        accounting.save()
        accounting.refresh_from_db()
        self.assertNotIn("abc-123", accounting.lexware_api_key_encrypted)
        self.assertEqual(decrypt_secret(accounting.lexware_api_key_encrypted), "abc-123-key-4567")
        self.assertEqual(accounting.lexware_api_key_hint, "…4567")
        self.assertIn("lexware_api_key_encrypted", export.SECRET_FIELDS["documents.accountingsettings"])
        self.assertNotIn("lexware_api_key_encrypted", export._fields(AccountingSettings))

    def test_the_rules_of_the_settings(self) -> None:
        accounting = AccountingSettings.load()
        accounting.lexware_enabled = True
        accounting.datev_revenue_accounts = {"19": "840"}
        accounting.lexware_categories = {"7": "nonsense"}
        accounting.datev_debitor_mode = DebitorMode.COLLECTIVE
        accounting.datev_collective_account = 9999
        with self.assertRaises(ValidationError) as caught:
            accounting.full_clean()
        self.assertEqual(
            caught.exception.message_dict,
            {
                "lexware_enabled": ["Trage zuerst den API-Schlüssel von Lexware Office ein."],
                "lexware_categories": ["„nonsense“ für 7 % ist keine Buchungskategorie von Lexware Office."],
                "datev_revenue_accounts": ["Das Erlöskonto für 19 % muss genau 4 Stellen haben."],
                "datev_collective_account": ["Ein Debitorenkonto liegt zwischen 10000 und 69999."],
            },
        )

    def test_accounts_per_tax_rate_and_chart(self) -> None:
        accounting = AccountingSettings.load()
        self.assertEqual([rate_key(Decimal(value)) for value in ("19.00", "7.50", "0", "16")], ["19", "7.5", "0", "16"])
        self.assertEqual([accounting.revenue_account_for(rate) for rate in ("19.00", "7", "0", "16")],
                         ["8400", "8300", "8336", ""])  # fmt: skip
        accounting.datev_chart = ChartOfAccounts.SKR04
        accounting.datev_account_length = 5
        accounting.datev_revenue_accounts = {"19": "44010"}
        self.assertEqual(
            [accounting.revenue_account_for(rate) for rate in ("19", "7", "0")], ["44010", "43000", "43360"]
        )
        self.assertEqual(accounting.debitor_range, (100000, 699999))

    def test_check_connection_keeps_the_income_categories(self) -> None:
        with FakeLexware() as server:
            server.switch_on()
            result = lexware.check_connection()
        self.assertEqual(
            (result.organization, result.tax_type, result.small_business), ("Licht & Ton GmbH", "net", False)
        )
        accounting = AccountingSettings.load()
        self.assertEqual([choice["name"] for choice in accounting.lexware_category_choices],
                         ["Einnahmen", "Dienstleistung", "Einnahmen EU"])  # fmt: skip
        self.assertIsNotNone(accounting.lexware_checked_at)


class DatevCase(AccountingCase):
    def setUp(self) -> None:
        super().setUp()
        accounting = AccountingSettings.load()
        accounting.datev_consultant_number, accounting.datev_client_number = 29098, 55003
        accounting.save()
        self.customer.name = "Bühnenwerk Köln"
        self.customer.save()

    def lines(self, result: datev.DatevFile) -> list[list[str]]:
        text = result.content.decode("cp1252")
        self.assertTrue(text.endswith("\r\n"))
        return [line.split(";") for line in text.removesuffix("\r\n").split("\r\n")]


class DatevBookingTests(DatevCase):
    """DOK-012: the Buchungsstapel."""

    def test_header_columns_and_one_line_per_invoice_and_tax_rate(self) -> None:
        invoice = self.invoice()
        cancellation = services.cancel_invoice(invoice)
        result = datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31), user=self.user)
        self.assertEqual(result.name, "EXTF_Buchungsstapel_20270301_20270331.csv")
        header, columns, *rows = self.lines(result)
        self.assertEqual(len(header), 31)
        self.assertEqual(header[:5], ['"EXTF"', "700", "21", '"Buchungsstapel"', "13"])
        self.assertRegex(header[5], r"^20270301\d{9}$")
        self.assertEqual(header[7:22], ['"RL"', '"luka"', "", "29098", "55003", "20270101", "4", "20270301",
                                        "20270331", '"Rechnungen 01.03.–31.03.2027"', "", "1", "0", "0", '"EUR"'])  # fmt: skip
        self.assertEqual(header[26], '"03"')
        self.assertEqual(len(columns), 125)
        self.assertEqual(columns[:3] + columns[6:11] + columns[13:14],
                         ["Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Konto",
                          "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel", "Belegdatum", "Belegfeld 1",
                          "Buchungstext"])  # fmt: skip
        self.assertTrue(all(len(row) == 125 for row in rows))
        debitor = self.customer.number
        self.assertEqual(
            [row[:11] + row[13:14] for row in rows],
            [
                ["238,00", '"S"', '"EUR"', "", "", "", debitor, "8400", '""', "0103", '"RE-2027-0001"',
                 '"Rechnung RE-2027-0001 Bühnenwerk Köln"'],
                ["53,50", '"S"', '"EUR"', "", "", "", debitor, "8300", '""', "0103", '"RE-2027-0001"',
                 '"Rechnung RE-2027-0001 Bühnenwerk Köln"'],
                ["238,00", '"H"', '"EUR"', "", "", "", debitor, "8400", '""', "0103", '"RE-2027-0002"',
                 '"Stornorechnung RE-2027-0002 Bühnenwerk Köln"'],
                ["53,50", '"H"', '"EUR"', "", "", "", debitor, "8300", '""', "0103", '"RE-2027-0002"',
                 '"Stornorechnung RE-2027-0002 Bühnenwerk Köln"'],
            ],
        )  # fmt: skip
        # The gross amounts of the lines are those of the documents; umlauts in Windows-1252.
        self.assertEqual(sum(Decimal(row[0].replace(",", ".")) for row in rows[:2]), invoice.gross_total)
        self.assertEqual(cancellation.gross_total, -invoice.gross_total)
        self.assertIn("Bühnenwerk".encode("cp1252"), result.content)
        self.assertEqual(result.count, 4)

    def test_only_documents_of_the_period(self) -> None:
        self.invoice()
        result = datev.bookings_file(datetime.date(2027, 2, 1), datetime.date(2027, 2, 28))
        self.assertEqual((result.count, len(self.lines(result))), (0, 2))
        self.assertEqual(self.lines(result)[0][8], '"Rentalars"')
        self.assertEqual([d.number for d in datev.documents_in(datetime.date(2027, 3, 1), datetime.date(2027, 3, 1))],
                         ["RE-2027-0001"])  # fmt: skip

    def test_debitor_accounts_by_offset_or_one_collective_account(self) -> None:
        self.invoice()
        accounting = AccountingSettings.load()
        accounting.datev_debitor_offset = 10000
        accounting.save()
        rows = self.lines(datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31)))[2:]
        self.assertEqual({row[6] for row in rows}, {str(int(self.customer.number) + 10000)})
        accounting.datev_debitor_offset = 60000
        accounting.save()
        with self.assertRaisesMessage(ValidationError, "würde das Debitorenkonto 70001 bekommen"):
            datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))
        accounting.datev_debitor_mode, accounting.datev_collective_account = DebitorMode.COLLECTIVE, 10000
        accounting.save()
        rows = self.lines(datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31)))[2:]
        self.assertEqual({row[6] for row in rows}, {"10000"})
        with self.assertRaisesMessage(ValidationError, "auf einem Sammelkonto"):
            datev.debitors_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))

    def test_a_customer_number_with_letters_cannot_be_a_debitor(self) -> None:
        Customer.objects.filter(pk=self.customer.pk).update(number="K-17")
        self.project.refresh_from_db()
        self.invoice()
        with self.assertRaisesMessage(ValidationError, "Kunde „Bühnenwerk Köln“ hat die Nummer „K-17“"):
            datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))

    def test_a_tax_rate_without_revenue_account_stops_the_export(self) -> None:
        sixteen = TaxRate.objects.create(name="16 %", rate=Decimal("16.00"))
        add_line(
            self.project, make_product("L-030", "Altlast", price="10.00", billing_mode="flat", tax_rate=sixteen), 1
        )
        self.invoice()
        with self.assertRaisesMessage(ValidationError, "Für den Steuersatz von 16 % gibt es kein Erlöskonto."):
            datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))
        accounting = AccountingSettings.load()
        accounting.datev_revenue_accounts = {"16": "8410"}
        accounting.save()
        rows = self.lines(datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31)))[2:]
        self.assertEqual([row[7] for row in rows], ["8400", "8410", "8300"])

    def test_tax_free_services_to_another_eu_country_carry_the_vat_id(self) -> None:
        tax_free = TaxRate.objects.get(rate=0)
        customer = prepare(make_customer("Teatro Verde S.r.l."))
        customer.vat_id = "IT12345678901"
        customer.save()
        project = make_project("Festival", customer=customer, start=at(10, 8), end=at(12, 18))
        add_line(project, make_product("L-040", "Licht EU", price="500.00", billing_mode="flat", tax_rate=tax_free), 1)
        self.invoice(project)
        row = self.lines(datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31)))[2]
        self.assertEqual((row[0], row[7], row[39]), ("500,00", "8336", '"IT12345678901"'))

    def test_the_period_lies_within_one_fiscal_year(self) -> None:
        accounting = AccountingSettings.load()
        accounting.datev_fiscal_year_start = 7
        accounting.save()
        with self.assertRaisesMessage(ValidationError, "innerhalb eines Wirtschaftsjahres"):
            datev.bookings_file(datetime.date(2027, 6, 1), datetime.date(2027, 7, 31))
        header = self.lines(datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31)))[0]
        self.assertEqual(header[12], "20260701")
        with self.assertRaisesMessage(ValidationError, "endet, bevor er beginnt"):
            datev.bookings_file(datetime.date(2027, 3, 31), datetime.date(2027, 3, 1))
        accounting.datev_consultant_number = None
        accounting.save()
        with self.assertRaisesMessage(ValidationError, "Beraternummer und die Mandantennummer"):
            datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))

    def test_texts_in_windows_1252(self) -> None:
        self.assertEqual(datev._ansi('Zoë „Bühne“ – Łódź;\n"x"'), "Zoë „Bühne“ – Lódz; 'x'")
        self.assertEqual(datev._document_number("RE_2027.0001"), "RE-2027-0001")
        self.assertEqual(datev._amount(Decimal("-1234.5")), "1234,50")


class DatevDebitorTests(DatevCase):
    def test_the_customers_of_the_period_as_debitor_accounts(self) -> None:
        self.customer.vat_id, self.customer.phone, self.customer.payment_terms_days = "DE123456789", "0221 1", 30
        self.customer.save()
        private = prepare(make_customer("Anna Maria Beispiel"))
        private.kind = CustomerKind.PRIVATE
        private.save()
        self.invoice()
        project = make_project("Hochzeit", customer=private, start=at(10, 8), end=at(12, 18))
        add_line(project, make_product("L-050", "Lichterkette", price="80.00", billing_mode="flat"), 1)
        self.invoice(project)
        result = datev.debitors_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31), user=self.user)
        self.assertEqual(result.name, "EXTF_Debitoren_20270301_20270331.csv")
        header, columns, company, person = self.lines(result)
        self.assertEqual(header[:5], ['"EXTF"', "700", "16", '"Debitoren/Kreditoren"', "5"])
        self.assertEqual(header[10:17], ["29098", "55003", "20270101", "4", "", "", '"Kunden aus Rentalars"'])
        self.assertEqual(len(columns), 254)
        self.assertEqual((columns[0], columns[1], columns[98], columns[253]),
                         ("Konto", "Name (Adressatentyp Unternehmen)", "Kundennummer", "Letzte Frist"))  # fmt: skip
        self.assertTrue(len(company) == len(person) == 254)
        filled = {index: value for index, value in enumerate(company) if value}
        self.assertEqual(
            filled,
            {
                0: self.customer.number,
                1: '"Bühnenwerk Köln"',
                6: "2",
                8: '"DE"',
                9: '"123456789"',
                14: '"STR"',
                15: '"Markt 1"',
                17: '"12345"',
                18: '"Musterstadt"',
                19: '"DE"',
                28: '"0221 1"',
                32: '"a@b.example"',
                98: f'"{self.customer.number}"',
                109: "30",
            },
        )
        self.assertEqual(
            (person[0], person[3], person[4], person[6]), (private.number, '"Beispiel"', '"Anna Maria"', "1")
        )
