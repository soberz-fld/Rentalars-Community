# SPDX-License-Identifier: GPL-3.0-or-later
"""The archive of vouchers (DOK-043), the export for an audit and the procedure documentation (DOK-046)."""

from __future__ import annotations

import datetime
import io
import zipfile

from django.core.exceptions import ValidationError
from django.utils import timezone

from rentalars.core import selfcheck
from rentalars.documents import archive, audit_export, procedure
from rentalars.documents.models import AccountingSettings, ArchiveRecord, ArchiveSource, ArchiveStatus
from rentalars.incoming import services as incoming_services
from rentalars.incoming.models import IncomingInvoice
from tests.unit.test_060_accounting import AccountingCase
from tests.unit.test_100_incoming import make_invoice


class ArchiveTests(AccountingCase):
    def test_a_document_is_archived_with_its_checksum_and_retention(self) -> None:
        document = self.invoice()
        self.assertEqual(archive.register_missing(), 1)
        record = ArchiveRecord.objects.get(source=ArchiveSource.DOCUMENT, source_id=document.pk)
        self.assertEqual(record.status, ArchiveStatus.OK)
        self.assertEqual(record.files[0]["sha256"], document.sha256)
        self.assertEqual(record.retain_until, datetime.date(2035, 12, 31))  # 2027 + 8 years
        self.assertEqual(archive.register_missing(), 0)

    def test_the_period_follows_the_settings_and_the_kind(self) -> None:
        from rentalars.documents import services
        from rentalars.documents.models import DocumentKind

        row = AccountingSettings.load()
        row.retention_invoice_years, row.retention_letter_years = 10, 3
        row.save()
        offer = services.create_document(self.project, DocumentKind.OFFER, user=self.user)
        invoice = self.invoice()
        archive.register_missing()
        self.assertEqual(
            ArchiveRecord.objects.get(source_id=offer.pk, source="document").retain_until, datetime.date(2030, 12, 31)
        )
        self.assertEqual(
            ArchiveRecord.objects.get(source_id=invoice.pk, source="document").retain_until, datetime.date(2037, 12, 31)
        )

    def test_a_changed_file_is_found_and_the_self_check_turns_red(self) -> None:
        document = self.invoice()
        archive.register_missing()
        with document.file.storage.open(document.file.name, "wb") as handle:
            handle.write(b"changed")
        result = archive.run(everything=True)
        self.assertEqual(result.problems, 1)
        record = ArchiveRecord.objects.get()
        self.assertEqual(record.status, ArchiveStatus.CHANGED)
        report = selfcheck.Report()
        selfcheck._archive(report)
        self.assertEqual(report.worst, selfcheck.ERROR)

    def test_a_missing_file_is_found(self) -> None:
        document = self.invoice()
        archive.register_missing()
        document.file.storage.delete(document.file.name)
        archive.run(everything=True)
        self.assertEqual(ArchiveRecord.objects.get().status, ArchiveStatus.MISSING)

    def test_the_nightly_run_checks_every_file_within_the_period(self) -> None:
        from rentalars.documents import services
        from rentalars.documents.models import DocumentKind

        for _index in range(6):
            services.create_document(self.project, DocumentKind.OFFER, user=self.user)
        archive.register_missing()
        row = AccountingSettings.load()
        row.archive_check_days = 3
        row.save()
        ArchiveRecord.objects.update(last_checked_at=timezone.now() - datetime.timedelta(days=5))
        archive.run()
        self.assertEqual(
            ArchiveRecord.objects.filter(last_checked_at__gte=timezone.now() - datetime.timedelta(minutes=5)).count(),
            -(-ArchiveRecord.objects.count() // 3),
        )

    def test_an_incoming_invoice_is_archived_after_the_grace_time_and_then_kept(self) -> None:
        invoice = make_invoice()
        self.assertEqual(archive.register_missing(), 0)  # a new upload may still be deleted
        IncomingInvoice.objects.filter(pk=invoice.pk).update(created_at=timezone.now() - datetime.timedelta(days=2))
        self.assertEqual(archive.register_missing(), 1)
        invoice.refresh_from_db()
        with self.assertRaises(ValidationError):
            incoming_services.delete_invoice(invoice)
        record = ArchiveRecord.objects.get(source=ArchiveSource.INCOMING)
        ArchiveRecord.objects.filter(pk=record.pk).update(retain_until=datetime.date(2027, 2, 28))
        incoming_services.delete_invoice(invoice)  # the period is over
        archive.run(everything=True)
        self.assertEqual(ArchiveRecord.objects.get().status, ArchiveStatus.DELETED)
        self.assertEqual(archive.problems().count(), 0)

    def test_a_deleted_voucher_inside_the_period_is_a_finding(self) -> None:
        invoice = make_invoice()
        IncomingInvoice.objects.filter(pk=invoice.pk).update(created_at=timezone.now() - datetime.timedelta(days=2))
        archive.register_missing()
        IncomingInvoice.objects.filter(pk=invoice.pk).delete()  # past the guard, e.g. by hand in the database
        archive.run(everything=True)
        self.assertEqual(ArchiveRecord.objects.get().status, ArchiveStatus.MISSING)

    def test_the_daily_maintenance_runs_the_archive(self) -> None:
        from django.core.management import call_command

        self.invoice()
        out = io.StringIO()
        call_command("run_daily_maintenance", stdout=out)
        self.assertIn("Archived 1 vouchers", out.getvalue())


class ExportTests(AccountingCase):
    def test_the_export_holds_tables_vouchers_and_checksums(self) -> None:
        document = self.invoice()
        archive.register_missing()
        body = audit_export.build(2027)
        with zipfile.ZipFile(body) as bundle:
            names = set(bundle.namelist())
            self.assertIn("index.xml", names)
            self.assertIn("SHA256SUMS", names)
            self.assertIn("tabellen/ausgangsbelege.csv", names)
            self.assertIn(f"belege/ausgang/{document.number}.pdf", names)
            self.assertIn(f"belege/ausgang/{document.number}.xml", names)
            table = bundle.read("tabellen/ausgangsbelege.csv").decode("utf-8")
            self.assertIn(document.number, table)
            sums = bundle.read("SHA256SUMS").decode()
            import hashlib

            for line in sums.splitlines():
                digest, path = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(bundle.read(path)).hexdigest(), digest, path)
            from xml.etree import ElementTree

            root = ElementTree.fromstring(bundle.read("index.xml"))
            self.assertEqual(root.tag, "DataSet")
            self.assertEqual(len(root.findall(".//Table")), 7)

    def test_the_period_limits_the_vouchers(self) -> None:
        self.invoice()
        with zipfile.ZipFile(audit_export.build(2026)) as bundle:
            self.assertFalse([n for n in bundle.namelist() if n.startswith("belege/")])
        with zipfile.ZipFile(audit_export.build(None)) as bundle:
            self.assertTrue([n for n in bundle.namelist() if n.startswith("belege/ausgang/")])


class ProcedureTests(AccountingCase):
    def test_the_documentation_names_the_settings(self) -> None:
        row = AccountingSettings.load()
        row.retention_invoice_years = 10
        row.save()
        text = procedure.as_markdown()
        self.assertIn("10", text)
        self.assertEqual(len(procedure.sections()), 5)
        pdf = procedure.render_pdf()
        self.assertTrue(pdf.startswith(b"%PDF"))
