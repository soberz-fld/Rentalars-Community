# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages of payments (DOK-048, DOK-042, DOK-045, DOK-043, DOK-046), open items, the check of e-invoices, the EÜR, the archive and the audit export (UIX)."""

from __future__ import annotations

import datetime
import io
import zipfile
from decimal import Decimal

from django.urls import reverse

from rentalars.documents import archive, payments
from rentalars.documents.models import ArchiveRecord, Document
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.models import IncomingInvoice
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import add, make_invoice

D = Decimal
TODAY = datetime.date(2027, 3, 1)


class PagesCase(UiTestCase, AccountingCase):
    def incoming(self) -> IncomingInvoice:
        invoice = make_invoice()
        add(invoice, "Miete", "1", "100.00", position_type="other", tax_rate=D("19.00"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            invoice_number="ER-7",
            total_net=D("100.00"),
            total_tax=D("19.00"),
            total_gross=D("119.00"),
            due_date=datetime.date(2027, 2, 1),
            invoice_date=datetime.date(2027, 1, 20),
        )
        invoice.refresh_from_db()
        return invoice


class PaymentPageTests(PagesCase):
    def test_a_payment_is_entered_and_voided_on_the_page_of_the_invoice(self) -> None:
        document = self.invoice()
        url = reverse("documents:payments", args=[document.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("291,50", page)
        data = form_data(self.client.get(url), "amount", amount="100,00", paid_on="2027-03-01")
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:800])
        self.assertEqual(payments.balance(Document.objects.get(pk=document.pk)).remaining, D("191.50"))
        payment = document.payments.get()
        self.client.post(url, {"action": "void", "payment": payment.pk, "reason": "wrong invoice"})
        self.assertEqual(payments.balance(Document.objects.get(pk=document.pk)).remaining, D("291.50"))
        self.assertIn("wrong invoice", self.assert_ok(self.client.get(url)))

    def test_the_invoice_page_offers_the_payments_and_the_check(self) -> None:
        document = self.invoice()
        page = self.assert_ok(self.client.get(reverse("documents:list", args=[self.project.pk])))
        self.assertIn(reverse("documents:payments", args=[document.pk]), page)
        response = self.client.post(reverse("documents:check", args=[document.pk]))
        self.assertEqual(response.status_code, 302)

    def test_the_incoming_invoice_page_shows_payments_and_the_check(self) -> None:
        invoice = self.incoming()
        url = reverse("incoming:payments", args=[invoice.pk])
        self.assertIn("119,00", self.assert_ok(self.client.get(url)))
        data = form_data(self.client.get(url), "amount", amount="119,00", paid_on="2027-03-01")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(incoming_payments.balance(IncomingInvoice.objects.get(pk=invoice.pk)).remaining, D("0.00"))
        detail = self.assert_ok(self.client.get(reverse("incoming:detail", args=[invoice.pk])))
        self.assertIn(url, detail)

    def test_only_who_may_see_and_change_gets_in(self) -> None:
        document = self.invoice()
        url = reverse("documents:payments", args=[document.pk])
        self.assertEqual(self.browser_for("lagerist", "Lager").get(url).status_code, 403)
        reader = self.browser_for("leser", "Nur-Lesen")
        self.assertEqual(
            reader.post(url, {"paid_on": "2027-03-01", "amount": "5,00", "method": "transfer"}).status_code, 403
        )


class OpenItemsPageTests(PagesCase):
    def test_open_items_list_both_sides_and_download(self) -> None:
        document = self.invoice()
        invoice = self.incoming()
        url = reverse("documents:open_items")
        out = self.assert_ok(self.client.get(url))
        self.assertIn(document.number, out)
        into = self.assert_ok(self.client.get(url + "?side=incoming"))
        self.assertIn("ER-7", into)
        csv = self.client.get(url + "?side=incoming&format=csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("ER-7", csv.content.decode("utf-8"))
        payments.record(document, paid_on=TODAY, amount=D("291.50"), user=self.user)
        self.assertNotIn(document.number, self.assert_ok(self.client.get(url)))
        self.assertEqual(invoice.pk, IncomingInvoice.objects.get(invoice_number="ER-7").pk)

    def test_the_pages_are_accessible(self) -> None:
        from tests.ui.test_accessibility import problems_of

        document = self.invoice()
        self.incoming()
        for path in (
            reverse("documents:open_items"),
            reverse("documents:payments", args=[document.pk]),
            reverse("documents:euer"),
            reverse("documents:archive"),
            reverse("documents:procedure"),
        ):
            self.assertEqual(problems_of(self.assert_ok(self.client.get(path))), [], path)


class EuerPageTests(PagesCase):
    def test_the_page_shows_the_year_and_gives_a_csv(self) -> None:
        document = self.invoice()
        payments.record(document, paid_on=TODAY, amount=D("291.50"), user=self.user)
        page = self.assert_ok(self.client.get(reverse("documents:euer") + "?year=2027"))
        self.assertIn("250,00", page)
        self.assertIn("41,50", page)
        csv = self.client.get(reverse("documents:euer") + "?year=2027&format=csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("RE-2027-0001", csv.content.decode("utf-8"))
        self.assertIn("euer-2027.csv", csv["Content-Disposition"])

    def test_a_bad_year_is_the_current_year(self) -> None:
        self.assert_ok(self.client.get(reverse("documents:euer") + "?year=abc"))

    def test_rights(self) -> None:
        for username, role in (("paula", "Projektleitung"), ("nora", "Nur-Lesen"), ("lars3", "Lager")):
            self.assertEqual(self.browser_for(username, role).get(reverse("documents:euer")).status_code, 403, role)


class ArchivePageTests(PagesCase):
    def test_the_archive_page_checks_and_exports(self) -> None:
        document = self.invoice()
        url = reverse("documents:archive")
        self.assertIn("1", self.assert_ok(self.client.get(url)))
        self.assertEqual(self.client.post(reverse("documents:archive_verify")).status_code, 302)
        self.assertEqual(ArchiveRecord.objects.count(), 1)
        page = self.assert_ok(self.client.get(url))
        self.assertIn(document.number, page)
        export = self.client.get(reverse("documents:audit_export") + "?year=2027")
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(b"".join(export.streaming_content))) as bundle:
            self.assertIn("SHA256SUMS", bundle.namelist())
        self.assertEqual(self.client.get(reverse("documents:audit_export") + "?year=all").status_code, 200)

    def test_a_changed_file_shows_on_the_page(self) -> None:
        document = self.invoice()
        archive.register_missing()
        with document.file.storage.open(document.file.name, "wb") as handle:
            handle.write(b"changed")
        self.client.post(reverse("documents:archive_verify"))
        page = self.assert_ok(self.client.get(reverse("documents:archive")))
        self.assertIn(document.number, page)
        filtered = self.assert_ok(self.client.get(reverse("documents:archive") + "?status=changed"))
        self.assertIn(document.number, filtered)

    def test_the_procedure_documentation_page_and_downloads(self) -> None:
        url = reverse("documents:procedure")
        self.assertIn("Verfahrensdokumentation", self.assert_ok(self.client.get(url)))
        pdf = self.client.get(url + "?format=pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertIn("# ", self.client.get(url + "?format=md").content.decode("utf-8"))
        self.assertEqual(self.client.get(url + "?format=x").status_code, 404)

    def test_rights(self) -> None:
        for name in ("archive", "audit_export", "procedure"):
            for username, role in (("paula", "Projektleitung"), ("nora", "Nur-Lesen")):
                self.assertEqual(
                    self.browser_for(f"{username}{name}", role).get(reverse(f"documents:{name}")).status_code,
                    403,
                    (name, role),
                )
        reader = self.browser_for("leser2", "Nur-Lesen")
        self.assertEqual(reader.post(reverse("documents:archive_verify")).status_code, 403)

    def test_the_settings_page_saves_the_books_section(self) -> None:
        url = reverse("documents:accounting")
        data = form_data(
            self.client.get(url),
            "books-invoice_format",
            **{"books-invoice_format": "zugferd", "books-retention_letter_years": "7"},
        )
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:500])
        from rentalars.documents.models import AccountingSettings

        row = AccountingSettings.load()
        self.assertEqual((row.invoice_format, row.retention_letter_years), ("zugferd", 7))
