# SPDX-License-Identifier: GPL-3.0-or-later
"""The API of payments (DOK-048), open items, the check of e-invoices, the EÜR, the archive and the audit export (API-014).

Every operation of the pages has its endpoint, with the rights of the page; the numbers are those of the pages.
"""

from __future__ import annotations

import datetime
import io
import zipfile
from decimal import Decimal

from rentalars.documents import archive, services
from rentalars.documents.models import AccountingSettings, DocumentKind, InvoiceFormat
from rentalars.incoming.models import IncomingInvoice
from tests.api.base import API, ApiTestCase
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal


class AccountingApiTests(AccountingCase, ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.nora = self.client_for("nora", "Nur-Lesen")
        self.lars_client = self.client_for("lars2", "Lager")

    # --- Outgoing payments ---

    def test_payments_of_an_outgoing_invoice(self) -> None:
        document = self.invoice()
        url = f"{API}/documents/{document.pk}/payments"
        body = self.admin.get(url).json()
        self.assertEqual(
            (body["balance"]["state"], body["balance"]["remaining"], body["payments"]), ("open", "291.50", [])
        )
        created = self.admin.post(
            url, {"paid_on": "2027-03-01", "amount": "100.00", "reference": "RE 1"}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["amount"], "100.00")
        body = self.admin.get(url).json()
        self.assertEqual((body["balance"]["state"], body["balance"]["remaining"]), ("partial", "191.50"))
        voided = self.admin.post(
            f"{API}/payments/{created.json()['id']}/void", {"reason": "typed twice"}, format="json"
        )
        self.assertEqual(voided.status_code, 200, voided.content)
        self.assertIsNotNone(voided.json()["voided_at"])
        self.assertEqual(self.admin.get(url).json()["balance"]["state"], "open")

    def test_voiding_without_the_rights_is_403_whether_or_not_the_payment_exists(self) -> None:
        self.assertEqual(self.nora.post(f"{API}/payments/999999/void", {"reason": "x"}, format="json").status_code, 403)

    def test_payment_errors_and_rights(self) -> None:
        document = self.invoice()
        url = f"{API}/documents/{document.pk}/payments"
        self.assert_error(
            self.admin.post(url, {"paid_on": "2999-01-01", "amount": "5.00"}, format="json"),
            400,
            "validation_error",
            "paid_on",
        )
        self.assert_error(
            self.admin.post(url, {"paid_on": "2027-03-01", "amount": "0"}, format="json"),
            400,
            "validation_error",
            "amount",
        )
        self.assertEqual(self.lars_client.get(url).status_code, 403)
        self.assertEqual(self.nora.post(url, {"paid_on": "2027-03-01", "amount": "5"}, format="json").status_code, 403)
        payment = self.admin.post(url, {"paid_on": "2027-03-01", "amount": "5.00"}, format="json").json()
        self.assert_error(
            self.admin.post(f"{API}/payments/{payment['id']}/void", {}, format="json"),
            400,
            "validation_error",
            "reason",
        )
        self.assertEqual(
            self.admin.post(f"{API}/payments/{payment['id']}/void", {"reason": "x"}, format="json").status_code, 200
        )
        self.assertEqual(
            self.admin.post(f"{API}/payments/{payment['id']}/void", {"reason": "x"}, format="json").status_code, 400
        )
        self.assertEqual(self.admin.get(f"{API}/documents/0/payments").status_code, 404)

    # --- Incoming payments ---

    def incoming(self) -> IncomingInvoice:
        invoice = make_invoice()
        add(invoice, "Miete", "1", "100.00", position_type="other", tax_rate=D("19.00"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number="ER-7",
            total_net=D("100.00"),
            total_tax=D("19.00"),
            total_gross=D("119.00"),
            due_date=datetime.date(2027, 2, 1),
        )
        invoice.refresh_from_db()
        return invoice

    def test_payments_of_an_incoming_invoice(self) -> None:
        invoice = self.incoming()
        url = f"{API}/incoming-invoices/{invoice.pk}/payments"
        self.assertEqual(self.admin.get(url).json()["balance"]["remaining"], "119.00")
        created = self.admin.post(url, {"paid_on": "2027-03-01", "amount": "119.00"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(self.admin.get(url).json()["balance"]["state"], "paid")
        response = self.admin.post(
            f"{API}/incoming-payments/{created.json()['id']}/void", {"reason": "bounced"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.admin.get(url).json()["balance"]["state"], "overdue" if False else "open")
        self.assertEqual(self.nora.post(url, {"paid_on": "2027-03-01", "amount": "5"}, format="json").status_code, 403)

    def test_an_incoming_invoice_without_totals_takes_no_payment(self) -> None:
        invoice = make_invoice()
        IncomingInvoice.objects.filter(pk=invoice.pk).update(total_gross=None)
        url = f"{API}/incoming-invoices/{invoice.pk}/payments"
        self.assertIsNone(self.admin.get(url).json()["balance"])
        self.assertEqual(self.admin.post(url, {"paid_on": "2027-03-01", "amount": "5"}, format="json").status_code, 400)

    # --- Open items ---

    def test_open_items_both_sides(self) -> None:
        document = self.invoice()
        invoice = self.incoming()
        out = self.admin.get(f"{API}/accounting/open-items").json()
        self.assertEqual((out["side"], len(out["items"]), out["total"]), ("outgoing", 1, "291.50"))
        self.assertEqual(out["items"][0]["number"], document.number)
        into = self.admin.get(f"{API}/accounting/open-items?side=incoming").json()
        self.assertEqual((len(into["items"]), into["total"], into["overdue"]), (1, "119.00", "119.00"))
        self.assertEqual(into["items"][0]["id"], invoice.pk)
        self.assertEqual(self.admin.get(f"{API}/accounting/open-items?side=x").status_code, 400)
        self.assertEqual(self.lars_client.get(f"{API}/accounting/open-items").status_code, 403)

    # --- The check of the e-invoice ---

    def test_the_check_of_an_outgoing_and_an_incoming_e_invoice(self) -> None:
        document = self.invoice()
        url = f"{API}/documents/{document.pk}/validation"
        got = self.admin.get(url).json()
        self.assertTrue(got["checked"] and got["ok"], got)
        self.assertEqual(got["errors"], 0)
        again = self.admin.post(url, format="json")
        self.assertEqual(again.status_code, 200, again.content)
        self.assertTrue(again.json()["ok"])
        self.assertEqual(self.nora.post(url, format="json").status_code, 403)
        invoice = make_invoice()
        into = f"{API}/incoming-invoices/{invoice.pk}/validation"
        self.assertFalse(self.admin.get(into).json()["checked"])
        self.assertEqual(self.admin.post(into, format="json").status_code, 400)  # a PDF without e-invoice

    # --- EÜR ---

    def test_the_euer(self) -> None:
        document = self.invoice()
        self.admin.post(
            f"{API}/documents/{document.pk}/payments", {"paid_on": "2027-03-01", "amount": "291.50"}, format="json"
        )
        body = self.admin.get(f"{API}/accounting/euer?year=2027").json()
        self.assertEqual(
            (body["year"], body["income_net"], body["tax_collected"], body["profit"]),
            (2027, "250.00", "41.50", "250.00"),
        )
        self.assertEqual(self.admin.get(f"{API}/accounting/euer?year=abc").status_code, 400)
        self.assertEqual(self.admin.get(f"{API}/accounting/euer?year=1999").status_code, 400)  # no silent fallback
        self.assertEqual(self.admin.get(f"{API}/accounting/euer").json()["year"], 2027)
        self.assertEqual(self.nora.get(f"{API}/accounting/euer").status_code, 403)
        self.assertEqual(self.lars_client.get(f"{API}/accounting/euer").status_code, 403)

    # --- Archive, export, procedure documentation ---

    def test_the_archive_and_its_check(self) -> None:
        self.invoice()
        before = self.admin.get(f"{API}/accounting/archive").json()
        self.assertEqual((before["total"], before["pending"]), (0, 1))
        done = self.admin.post(f"{API}/accounting/archive/verify", format="json")
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual((done.json()["registered"], done.json()["problems"]), (1, 0))
        after = self.admin.get(f"{API}/accounting/archive").json()
        self.assertEqual((after["total"], after["ok"], after["problems"]), (1, 1, []))
        self.assertEqual(self.nora.post(f"{API}/accounting/archive/verify", format="json").status_code, 403)

    def test_the_audit_export_and_the_procedure_documentation(self) -> None:
        document = self.invoice()
        archive.register_missing()
        response = self.admin.get(f"{API}/accounting/audit-export?year=2027")
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as bundle:
            self.assertIn(f"belege/ausgang/{document.number}.pdf", bundle.namelist())
        self.assertEqual(self.admin.get(f"{API}/accounting/audit-export?year=x").status_code, 400)
        self.assertEqual(self.nora.get(f"{API}/accounting/audit-export").status_code, 403)
        sections = self.admin.get(f"{API}/accounting/procedure").json()["sections"]
        self.assertEqual(len(sections), 5)
        self.assertTrue(self.admin.get(f"{API}/accounting/procedure?as=pdf").content.startswith(b"%PDF"))
        self.assertIn("#", self.admin.get(f"{API}/accounting/procedure?as=md").content.decode())
        self.assertEqual(self.admin.get(f"{API}/accounting/procedure?as=x").status_code, 400)

    # --- Settings ---

    def test_the_settings_carry_the_new_fields(self) -> None:
        got = self.admin.get(f"{API}/accounting/settings").json()
        self.assertEqual(
            (got["invoice_format"], got["retention_invoice_years"], got["small_business"]), ("xrechnung", 8, False)
        )
        changed = self.admin.patch(
            f"{API}/accounting/settings",
            {"invoice_format": InvoiceFormat.ZUGFERD, "small_business": True, "archive_check_days": 7},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(AccountingSettings.load().invoice_format, "zugferd")
        document = services.create_document(self.project, DocumentKind.INVOICE, user=self.user)
        self.assertEqual(document.einvoice_syntax, "zugferd")
        self.assertEqual(
            self.admin.patch(f"{API}/accounting/settings", {"retention_invoice_years": 0}, format="json").status_code,
            400,
        )
