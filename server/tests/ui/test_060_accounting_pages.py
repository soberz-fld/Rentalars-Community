# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of handing invoices to the accounting: DOK-011 (Lexware Office) and DOK-012 (DATEV export)."""

from __future__ import annotations

from django.urls import reverse

from rentalars.core.models import AccessLogEntry
from rentalars.documents import lexware, services
from rentalars.documents.models import AccountingSettings, DocumentKind
from tests.helpers import add_line, make_product, make_project, ready_for_invoices
from tests.lexware_fake import FakeLexware
from tests.ui.base import UiTestCase, form_data

KEY = "lexware-test-key-0123456789abcdef"


class AccountingPageCase(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.customer = ready_for_invoices()
        self.project = make_project("Stadtfest", customer=self.customer)
        add_line(self.project, make_product("L-010", "Lichtpauschale", price="100.00", billing_mode="flat"), 2)
        self.url = reverse("documents:accounting")


class AccountingPageTests(AccountingPageCase):
    def test_the_page_needs_the_settings_and_the_price_right(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        for text in ("Buchhaltung", "Lexware Office", "API-Schlüssel", "DATEV-Export", "Erlöskonto 19 %"):
            self.assertIn(text, page)
        administration = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(f'href="{self.url}"', administration)
        # Prices without the settings (Projektleitung, Nur-Lesen), the settings without prices: not allowed.
        for username, role in (("paula", "Projektleitung"), ("nora", "Nur-Lesen"), ("luka", "Lager")):
            browser = self.browser_for(username, role)
            self.assertEqual(browser.get(self.url).status_code, 403, role)
            self.assertEqual(browser.get(reverse("documents:datev_export")).status_code, 403, role)

    def test_the_pages_are_accessible(self) -> None:
        from tests.ui.test_accessibility import problems_of

        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        with FakeLexware() as server:
            server.switch_on()
            server.add_contact(int(self.customer.number), company="Ganz andere GmbH")
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                lexware.request_transfer(invoice)
            server.fail(401)
            self.client.post(reverse("documents:lexware_check"))
        for path in (self.url, reverse("documents:list", args=[self.project.pk])):
            self.assertEqual(problems_of(self.assert_ok(self.client.get(path))), [], path)

    def test_the_api_key_is_stored_encrypted_and_never_shown(self) -> None:
        refused = self.client.post(
            self.url, form_data(self.client.get(self.url), "lexware-api_key", **{"lexware-lexware_enabled": "on"})
        )
        self.assertIn("Trage zuerst den API-Schlüssel von Lexware Office ein.", refused.content.decode())
        self.assertFalse(AccountingSettings.load().lexware_enabled)

        data = form_data(
            self.client.get(self.url),
            "lexware-api_key",
            **{"lexware-lexware_enabled": "on", "lexware-api_key": KEY, "lexware-lexware_automatic": "on"},
        )
        saved = self.client.post(self.url, data, follow=True)
        self.assertIn("Die Einstellungen sind gespeichert.", self.messages_of(saved))
        accounting = AccountingSettings.objects.get()
        self.assertEqual((accounting.lexware_enabled, accounting.lexware_automatic), (True, True))
        self.assertEqual(accounting.lexware_api_key, KEY)
        page = self.assert_ok(self.client.get(self.url))
        self.assertNotIn(KEY, page)
        self.assertNotIn(accounting.lexware_api_key_encrypted, page)
        self.assertIn("gespeichert, endet auf …cdef", page)
        self.assertIn("an, sofort beim Erstellen einer Rechnung", page)
        # Saved again with an empty key field: the key stays.
        self.client.post(self.url, form_data(self.client.get(self.url), "lexware-api_key"))
        self.assertEqual(AccountingSettings.objects.get().lexware_api_key, KEY)

    def test_check_connection_and_choose_the_posting_categories(self) -> None:
        with FakeLexware() as server:
            server.switch_on()
            checked = self.client.post(reverse("documents:lexware_check"), follow=True)
            self.assertIn(
                "Verbunden mit Lexware Office: „Licht & Ton GmbH“. 3 Buchungskategorien für Einnahmen.",
                self.messages_of(checked),
            )
            page = self.assert_ok(checked)
            self.assertIn("Dienstleistung", page)
            self.assertIn("0 % Steuer", page)
            data = form_data(
                checked, "lexware-api_key", **{"lexware-category_0": "9075a4e3-66de-4795-a016-3889feca0d20"}
            )
            self.client.post(self.url, data)
            self.assertEqual(
                AccountingSettings.objects.get().lexware_categories, {"0": "9075a4e3-66de-4795-a016-3889feca0d20"}
            )
            server.fail(401)
            refused = self.client.post(reverse("documents:lexware_check"), follow=True)
        self.assertIn(
            "Lexware Office hat den API-Schlüssel abgelehnt. Prüfe ihn unter Einstellungen → Buchhaltung.",
            self.messages_of(refused),
        )


class HandingOverTests(AccountingPageCase):
    def test_an_invoice_is_handed_over_on_the_tab_documents(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        documents = reverse("documents:list", args=[self.project.pk])
        self.assertNotIn("An Lexware Office übergeben", self.assert_ok(self.client.get(documents)))
        with FakeLexware() as server:
            server.switch_on(collective=True)
            page = self.client.get(documents)
            self.assertIn("An Lexware Office übergeben", self.assert_ok(page))
            data = form_data(page, "next")
            done = self.client.post(reverse("documents:lexware_transfer", args=[invoice.pk]), data, follow=True)
        self.assertIn("RE-2027-0001 ist jetzt in Lexware Office.", self.messages_of(done))
        page = self.assert_ok(done)
        self.assertIn("Seit 01.03.2027", page)
        self.assertNotIn("An Lexware Office übergeben", page)
        self.assertEqual(len(server.vouchers), 1)
        again = self.client.post(reverse("documents:lexware_transfer", args=[invoice.pk]), follow=True)
        self.assertIn("RE-2027-0001 ist schon in Lexware Office.", self.messages_of(again))

    def test_who_may_hand_over(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        FakeLexware.switch_on(collective=True)
        address = reverse("documents:lexware_transfer", args=[invoice.pk])
        self.assertEqual(self.browser_for("luka", "Lager").post(address).status_code, 403)
        self.assertEqual(self.browser_for("nora", "Nur-Lesen").post(address).status_code, 403)
        manager = self.browser_for("paula", "Projektleitung")
        self.assertIn(
            "An Lexware Office übergeben",
            manager.get(reverse("documents:list", args=[self.project.pk])).content.decode(),
        )
        with FakeLexware():
            self.assertEqual(manager.post(address).status_code, 302)
        self.assertEqual(lexware.transfer_of(invoice).state, "done")

    def test_failed_handings_over_are_listed_and_can_be_repeated(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        with FakeLexware() as server:
            server.add_contact(int(self.customer.number), company="Ganz andere GmbH")
            server.switch_on()
            with self.assertLogs("rentalars.core.jobs", "ERROR"):
                failed = self.client.post(reverse("documents:lexware_transfer", args=[invoice.pk]), follow=True)
            self.assertIn("RE-2027-0001 wurde nicht übergeben: In Lexware Office gehört die Kundennummer",
                          self.messages_of(failed)[0])  # fmt: skip
            response = self.client.get(self.url)
            page = self.assert_ok(response)
            self.assertIn("„Ganz andere GmbH“", page)
            self.assertIn("Als neuen Kontakt übergeben", page)
            data = form_data(response, "new_contact")
            self.assertEqual(data["new_contact"], "1")
            done = self.client.post(reverse("documents:lexware_transfer", args=[invoice.pk]), data, follow=True)
        self.assertIn("RE-2027-0001 ist jetzt in Lexware Office.", self.messages_of(done))
        self.assertIn("Nichts wartet, nichts ist fehlgeschlagen.", self.assert_ok(done))
        self.assertIn("1 Dokument übergeben", self.assert_ok(done))


class DatevPageTests(AccountingPageCase):
    def test_settings_and_the_export_of_a_period(self) -> None:
        services.create_document(self.project, DocumentKind.INVOICE)
        address = reverse("documents:datev_export") + "?date_from=2027-03-01&date_to=2027-03-31&what=bookings"
        missing = self.client.get(address, follow=True)
        self.assertIn(
            "Trage zuerst die Beraternummer und die Mandantennummer unter Einstellungen → Buchhaltung ein.",
            self.messages_of(missing),
        )
        page = self.client.get(self.url)
        wrong = form_data(page, "datev-datev_consultant_number", **{"datev-account_19": "84"})
        self.assertIn("Ein Erlöskonto hat genau 4 Stellen.", self.client.post(self.url, wrong).content.decode())
        data = form_data(
            page,
            "datev-datev_consultant_number",
            **{
                "datev-datev_consultant_number": "29098",
                "datev-datev_client_number": "55003",
                "datev-account_19": "8401",
            },
        )
        self.assertIn(
            "Die Einstellungen sind gespeichert.", self.messages_of(self.client.post(self.url, data, follow=True))
        )
        accounting = AccountingSettings.objects.get()
        self.assertEqual(
            (accounting.datev_consultant_number, accounting.datev_client_number, accounting.datev_revenue_accounts),
            (29098, 55003, {"19": "8401"}),
        )
        response = self.client.get(address)
        self.assertEqual(response["Content-Type"], "text/csv; charset=windows-1252")
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="EXTF_Buchungsstapel_20270301_20270331.csv"'
        )
        lines = response.content.decode("cp1252").split("\r\n")
        self.assertTrue(lines[0].startswith('"EXTF";700;21;"Buchungsstapel";13;'))
        self.assertIn(f'238,00;"S";"EUR";;;;{self.customer.number};8401;', lines[2])
        # AUT-028: an export of invoices is noted in the access log.
        self.assertTrue(
            AccessLogEntry.objects.filter(action="export", label__startswith="EXTF_Buchungsstapel").exists()
        )
        debitors = self.client.get(address.replace("bookings", "debitors"))
        self.assertIn(b'"Debitoren/Kreditoren";5', debitors.content)
        self.assertIn(b'"Stadtwerke Musterstadt"', debitors.content)

    def test_the_page_says_which_invoices_a_period_holds(self) -> None:
        services.create_document(self.project, DocumentKind.INVOICE)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('hx-get="/administration/accounting/datev/preview/"', page)
        self.assertIn("Keine Rechnungen vom 01.02.2027 bis 28.02.2027.", page)
        preview = self.htmx(
            "get", reverse("documents:datev_preview"), {"date_from": "2027-03-01", "date_to": "2027-03-31"}
        )
        text = self.assert_ok(preview)
        self.assertIn("Vom 01.03.2027 bis 31.03.2027: 1 Rechnung:", text)
        self.assertIn("RE-2027-0001", text)
        self.assertIn("Wähle einen Zeitraum.", self.assert_ok(self.htmx("get", reverse("documents:datev_preview"), {})))
