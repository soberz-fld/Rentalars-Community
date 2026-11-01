# SPDX-License-Identifier: GPL-3.0-or-later
"""The export for an audit as a task in the background (DOK-054)."""

from __future__ import annotations

import datetime
import io
import zipfile
from decimal import Decimal

from django.urls import reverse

from rentalars.core.models import BackgroundJob, JobStatus
from rentalars.documents import audit_export
from tests.api.base import API, ApiTestCase
from tests.ui.test_112_pages import PagesCase
from tests.unit.test_060_accounting import AccountingCase


class AuditJobServiceTests(AccountingCase):
    def test_the_task_makes_the_same_zip_and_reports_progress(self) -> None:
        self.invoice()
        job = audit_export.start(2027, user=self.user)
        self.assertEqual((job.status, job.progress), (JobStatus.DONE, 100))
        self.assertEqual(job.result_name, "pruefexport-2027.zip")
        with zipfile.ZipFile(job.result_file) as bundle:
            names = set(bundle.namelist())
            made = {name: bundle.read(name) for name in names}
        with zipfile.ZipFile(audit_export.build(2027)) as bundle:
            self.assertEqual(names, set(bundle.namelist()))
            again = {name: bundle.read(name) for name in names}
        self.assertIn("SHA256SUMS", names)
        # The same content, file by file (the invoice is in it).
        self.assertEqual(made, again)
        self.assertIn(b"RE-2027-0001", b"".join(made.values()))

    def test_all_years_and_progress_steps(self) -> None:
        self.invoice()
        steps: list[int] = []
        audit_export.build(None, progress=steps.append).close()
        self.assertEqual(steps[0], 5)
        self.assertEqual(steps, sorted(steps))
        self.assertLessEqual(steps[-1], 95)
        job = audit_export.start(None, user=self.user)
        self.assertEqual(job.result_name, "pruefexport-alle.zip")

    def test_a_failure_leaves_no_file_behind(self) -> None:
        import glob
        import tempfile
        from unittest import mock

        before = set(glob.glob(f"{tempfile.gettempdir()}/rentalars-audit-*.zip"))
        with mock.patch.object(audit_export, "build", side_effect=RuntimeError("disk full")):
            job = audit_export.start(2027, user=self.user)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(set(glob.glob(f"{tempfile.gettempdir()}/rentalars-audit-*.zip")), before)


class AuditCsvTests(AccountingCase):
    def test_a_text_is_no_formula_but_a_number_stays_a_number(self) -> None:
        text = audit_export._text
        self.assertEqual(text('=HYPERLINK("x")'), '\'=HYPERLINK("x")')
        self.assertEqual(text("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(text("-12.50"), "-12.50")
        self.assertEqual(text(Decimal("-12.5")), "-12.50")
        self.assertEqual(text("-Kabel"), "'-Kabel")

    def test_the_other_csv_files_of_the_books_use_the_same_protection(self) -> None:
        from rentalars.core.tables import formula_safe

        self.assertEqual(formula_safe("=1+1"), "'=1+1")
        self.assertEqual(formula_safe("-3,50"), "-3,50")
        self.assertEqual(formula_safe(5), 5)
        self.assertEqual(formula_safe("Kabel"), "Kabel")

    def test_the_exchange_rate_is_not_rounded(self) -> None:
        from rentalars.incoming.models import IncomingInvoice
        from tests.unit.test_100_incoming import add, make_invoice

        invoice = make_invoice()
        add(invoice, "Miete", "1", "100.00", position_type="other", tax_rate=Decimal("19.00"))
        IncomingInvoice.objects.filter(pk=invoice.pk).update(
            currency="USD", exchange_rate=Decimal("1.087654"), invoice_date=datetime.date(2027, 3, 1)
        )
        with zipfile.ZipFile(audit_export.build(2027)) as bundle:
            files = {name: bundle.read(name).decode("utf-8") for name in bundle.namelist() if name.endswith(".csv")}
        self.assertTrue(any("1.087654" in content for content in files.values()), sorted(files))


class AuditJobPageTests(PagesCase):
    def test_the_archive_page_starts_the_task(self) -> None:
        self.invoice()
        page = self.assert_ok(self.client.get(reverse("documents:archive")))
        self.assertIn(reverse("documents:audit_export_start"), page)
        response = self.client.post(reverse("documents:audit_export_start"), {"year": "2027"})
        job = BackgroundJob.objects.get(kind="audit_export")
        self.assertRedirects(response, reverse("core:job", args=[job.pk]), fetch_redirect_response=False)
        result = self.client.get(reverse("core:job_result", args=[job.pk]))
        with zipfile.ZipFile(io.BytesIO(b"".join(result.streaming_content))) as bundle:
            self.assertIn("SHA256SUMS", bundle.namelist())
        self.assertEqual(self.client.get(reverse("documents:audit_export_start")).status_code, 405)

    def test_only_who_may_see_the_books(self) -> None:
        for username, role in (("paula", "Projektleitung"), ("nora", "Nur-Lesen")):
            browser = self.browser_for(username + "job", role)
            self.assertEqual(browser.post(reverse("documents:audit_export_start"), {"year": "2027"}).status_code, 403)
        self.assertFalse(BackgroundJob.objects.exists())


class AuditJobApiTests(AccountingCase, ApiTestCase):
    def test_start_and_fetch(self) -> None:
        self.invoice()
        response = self.admin.post(f"{API}/accounting/audit-export", {"year": "2027"}, format="json")
        self.assertEqual(response.status_code, 202, response.content)
        job_id = response.json()["id"]
        self.assertEqual(self.admin.get(f"{API}/jobs/{job_id}").json()["status"], "done")
        result = self.admin.get(f"{API}/jobs/{job_id}/result")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.admin.post(f"{API}/accounting/audit-export", {}, format="json").status_code, 202)
        self.assert_error(
            self.admin.post(f"{API}/accounting/audit-export", {"year": "x"}, format="json"), 400, "validation_error"
        )
        self.assertEqual(
            self.client_for("nora", "Nur-Lesen").post(f"{API}/accounting/audit-export", {}, format="json").status_code,
            403,
        )
