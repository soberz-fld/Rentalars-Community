# SPDX-License-Identifier: GPL-3.0-or-later
""" "Import alter Projekte auf Basis von Rechnungen" – old projects from the PDF invoices of the old system. (PRJ-130)

The requirement: old projects are imported on the basis of invoices. Decided: the user uploads their own *outgoing* invoices of past
projects as PDFs; the AI reads them; a preview comes first and the adoption is confirmed explicitly, as with
"Kauf einpflegen". Without AI a pattern reader makes the feature usable with manual correction.

* Upload of one or several PDFs (size, number, type, duplicates in the upload and against earlier imports).
* Reading: text of the PDF only (no scans), AI answer checked strictly, patterns as fallback; customer matched against
  the customers of the system (proposed, never created unseen), products suggested.
* Checks as warnings (sum of the positions against the totals, tax) and errors (number missing or taken or inside the
  live number range, unknown tax rate, no customer …).
* Confirmation: exactly what will be created; per project one transaction; a closed project with free lines and a
  historic invoice with the original PDF; no mail, no task, no notification, no webhook, no reservation, no number
  from the live ranges; left out of the DATEV export unless asked for.
* Provenance, idempotence, joining invoices into one project, partial confirmation, undo.
* Rights and the API (API-002, API-014).
"""

from __future__ import annotations

import functools
import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.ai import legacy_invoices
from rentalars.ai.models import AICall, AISettings, Source
from rentalars.api.models import Webhook, WebhookDelivery
from rentalars.automations.models import Action, Automation, AutomationRun, Recipient, Trigger
from rentalars.core.models import AuditLogEntry, NumberRange, NumberRangeKey
from rentalars.customers.models import Customer
from rentalars.documents.models import Document
from rentalars.notifications.models import Notification
from rentalars.projects import legacy_import, legacy_text
from rentalars.projects.legacy_draft import Draft, Line, decimal_of
from rentalars.projects.legacy_models import ItemState, LegacyImportBatch, LegacyImportItem
from rentalars.projects.models import InvoiceMark, Project, ProjectStatus
from tests.ai_fake import FakeModelServer, write_local_file
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, make_customer, make_user, ready_for_invoices
from tests.ui.base import UiTestCase, form_data, forms_of

#: The customer of the sample invoices – a town other than the company's.
CUSTOMER_LINES = ("Beispielburg Stadtwerke AG", "Frau Meier", "Rathausplatz 2", "54321 Beispielburg")


def _money(value: Decimal) -> str:
    """A German amount: 1.234,50."""
    whole, cents = f"{value:.2f}".split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return ".".join(reversed(groups)) + "," + cents


@functools.cache
def invoice_pdf(
    number: str = "2023-0042",
    date: str = "15.06.2023",
    positions: tuple[tuple[str, str, str, str], ...] = (
        ("LED Scheinwerfer PAR 64", "8", "Stk", "25.00"),
        ("Mischpult Behringer X32", "1", "Stk", "180.00"),
        ("Techniker Aufbau", "6", "Std", "55.00"),
    ),
    event: str = "Stadtfest 2023",
    period: str = "10.06.2023 - 12.06.2023",
    vat: str = "DE123456789",
    rate: int = 19,
    wrong_total: str = "",
) -> bytes:
    """An old outgoing invoice as a PDF with a text layer, made with WeasyPrint."""
    from weasyprint import HTML

    rows, net = [], Decimal(0)
    for index, (title, quantity, unit, price) in enumerate(positions, start=1):
        amount = Decimal(quantity) * Decimal(price)
        net += amount
        rows.append(
            f"<tr><td>{index}</td><td>{title}</td><td>{quantity}</td><td>{unit}</td>"
            f"<td>{_money(Decimal(price))}</td><td>{_money(amount)}</td></tr>"
        )
    tax = (net * rate / 100).quantize(Decimal("0.01"))
    shown_net = Decimal(wrong_total) if wrong_total else net
    html = f"""<html><body style="font-size: 11px">
<p>Licht &amp; Ton Altsystem GmbH · Hafen 1 · 12345 Musterstadt</p>
<p>{"<br>".join(CUSTOMER_LINES)}</p>
<h1>Rechnung</h1>
<p>Rechnungsnummer: {number}<br>Rechnungsdatum: {date}<br>Leistungszeitraum: {period}<br>Veranstaltung: {event}<br>
USt-IdNr.: {vat}</p>
<table><tr><th>Pos.</th><th>Bezeichnung</th><th>Menge</th><th>Einheit</th><th>Einzelpreis</th><th>Gesamt</th></tr>
{"".join(rows)}</table>
<p>Summe netto {_money(shown_net)} EUR<br>zzgl. {rate} % USt {_money(tax)} EUR<br>
Gesamtbetrag {_money(net + tax)} EUR</p>
</body></html>"""
    return HTML(string=html).write_pdf()


@functools.cache
def scanned_pdf() -> bytes:
    """A PDF without text – like a scan."""
    from weasyprint import HTML

    return HTML(string='<div style="width:200px;height:100px;background:#333"></div>').write_pdf()


def upload(name: str = "rechnung.pdf", content: bytes | None = None) -> SimpleUploadedFile:
    """An uploaded PDF (the first sample invoice by default)."""
    return SimpleUploadedFile(name, content if content is not None else invoice_pdf(), "application/pdf")


class FilesMixin:
    """Uploads and documents go to folders of the test."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)  # type: ignore[attr-defined]
        override = override_settings(DATA_DIR=folder, MEDIA_ROOT=str(folder / "media"), SERVE_MEDIA_VIA_NGINX=False)
        override.enable()
        self.addCleanup(override.disable)  # type: ignore[attr-defined]
        self.data_dir = folder


class AIMixin:
    """The fake model server as the local AI; reading invoices off until a test switches it on."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)  # type: ignore[attr-defined]
        self.local_file = folder / "ai-local.conf"
        override = override_settings(RENTALARS_AI_LOCAL_FILE=str(self.local_file))
        override.enable()
        self.addCleanup(override.disable)  # type: ignore[attr-defined]
        self.fake = FakeModelServer().__enter__()
        self.addCleanup(self.fake.__exit__)  # type: ignore[attr-defined]

    def reading_on(self, answer: str) -> None:
        write_local_file(self.local_file, self.fake.url)
        self.fake.answer = answer
        ai_settings = AISettings.load()
        ai_settings.invoice_source = Source.LOCAL
        ai_settings.save()


def answer_of(**changes: Any) -> str:
    """What a well-behaved model answers for the first sample invoice."""
    data: dict[str, Any] = {
        "customer": {
            "name": "Beispielburg Stadtwerke AG",
            "name_addition": "Frau Meier",
            "street": "Rathausplatz 2",
            "postal_code": "54321",
            "city": "Beispielburg",
            "country": None,
            "vat_id": "DE 123 456 789",
        },
        "invoice_number": "2023-0042",
        "invoice_date": "2023-06-15",
        "service_start": "2023-06-10",
        "service_end": "2023-06-12",
        "event_name": "Stadtfest 2023",
        "venue": "Marktplatz",
        "currency": "EUR",
        "prices_include_tax": False,
        "tax_rate": 19,
        "paid_on": None,
        "total_net": "710,00",
        "total_tax": "134,90",
        "total_gross": "844,90",
        "positions": [
            {"description": "LED Scheinwerfer PAR 64", "quantity": "8", "unit": "Stk", "unit_price": "25,00",
             "tax_rate": 19, "amount": "200,00"},
            {"description": "Mischpult Behringer X32", "quantity": "1", "unit": "Stk", "unit_price": "180,00",
             "tax_rate": 19, "amount": "180,00"},
            {"description": "Techniker Aufbau", "quantity": "6", "unit": "Std", "unit_price": "55,00",
             "tax_rate": 19, "amount": "330,00"},
        ],
    }  # fmt: skip
    data.update(changes)
    return "```json\n" + json.dumps(data) + "\n```"


def days_of(project: Project) -> tuple[str, str]:
    """First and last day of a project in the time zone of the installation."""
    from django.utils import timezone

    return timezone.localdate(project.start).isoformat(), timezone.localdate(project.end).isoformat()


def power_user(name: str = "lena") -> Any:
    """A user who may use the import: prices and write access to every project."""
    role = Role.objects.create(
        name=f"Altprojekte {name}",
        module_levels={Module.PROJECTS: int(Level.WRITE), Module.CUSTOMERS: int(Level.WRITE)},
        special_rights=[SpecialRight.PRICES],
    )
    user = make_user(name)
    user.roles.add(role)
    return user


# --- Patterns, answers ----------------------------------------------------------------------------------------------


class PatternReadingTests(FilesMixin, RentalarsTestCase):
    """Without AI: the text of the PDF is searched by patterns; everything is only a proposal."""

    def setUp(self) -> None:
        super().setUp()
        ready_for_invoices()

    def text(self, **options: Any) -> str:
        from rentalars.material import purchases

        path = self.data_dir / "x.pdf"
        path.write_bytes(invoice_pdf(**options))
        return str(purchases.invoice_text(path))

    def test_head_customer_positions_and_totals(self) -> None:
        draft = legacy_text.draft_from_text(self.text())
        self.assertEqual(draft.source, "text")
        self.assertEqual((draft.invoice.number, str(draft.invoice.date)), ("2023-0042", "2023-06-15"))
        self.assertEqual(
            (str(draft.invoice.service_start), str(draft.invoice.service_end)), ("2023-06-10", "2023-06-12")
        )
        self.assertEqual(draft.invoice.event_name, "Stadtfest 2023")
        self.assertEqual(draft.customer.name, "Beispielburg Stadtwerke AG")
        self.assertEqual(
            (draft.customer.street, draft.customer.postal_code, draft.customer.city),
            ("Rathausplatz 2", "54321", "Beispielburg"),
        )
        self.assertEqual(draft.customer.vat_id, "DE123456789")  # not the company's own, nothing glued on
        self.assertEqual(
            [(line.title, line.quantity, line.unit, line.unit_price) for line in draft.lines],
            [
                ("LED Scheinwerfer PAR 64", Decimal("8"), "Stk", Decimal("25.00")),
                ("Mischpult Behringer X32", Decimal("1"), "Stk", Decimal("180.00")),
                ("Techniker Aufbau", Decimal("6"), "Std", Decimal("55.00")),
            ],
        )
        self.assertTrue(all(line.tax_percent == Decimal("19") for line in draft.lines))
        self.assertEqual(
            (draft.totals.net, draft.totals.tax, draft.totals.gross),
            (Decimal("710.00"), Decimal("134.90"), Decimal("844.90")),
        )

    def test_a_customer_in_the_town_of_the_company_is_found(self) -> None:
        from rentalars.projects import legacy_text as reader

        text = "Licht & Ton GmbH\nHafen 1\n12345 Musterstadt\nRechnung Nr. 7\nStadtwerke Nebenan\nMarkt 3\n12345 Musterstadt\n1 Kabel 2 Stk 5,00 10,00"
        self.assertEqual(reader.customer_from_text(text).name, "Stadtwerke Nebenan")

    def test_nothing_readable_gives_an_empty_proposal_to_type_in(self) -> None:
        draft = legacy_text.draft_from_text("Irgendein Text ohne Zahlen und Struktur")
        self.assertEqual((draft.invoice.number, draft.lines), ("", []))


class AnswerParsingTests(RentalarsTestCase):
    """The answer of the model is data from outside: strict keys, types, lengths and numbers."""

    def parse(self, **changes: Any) -> Draft:
        return legacy_invoices.parse_answer(answer_of(**changes))

    def test_a_good_answer(self) -> None:
        draft = self.parse()
        self.assertEqual(draft.source, "ai")
        self.assertEqual(draft.customer.vat_id, "DE123456789")
        self.assertEqual(draft.invoice.venue, "Marktplatz")
        self.assertEqual(len(draft.lines), 3)
        self.assertEqual(draft.lines[0].unit_price, Decimal("25.00"))
        self.assertEqual(draft.totals.gross, Decimal("844.90"))

    def test_nothing_in_it_reaches_further_than_the_preview(self) -> None:
        draft = self.parse(
            customer_id=1, project="X", role="admin", status="paid", __class__="x",
            customer={"name": "Muster GmbH", "customer_id": 7, "is_staff": True},
        )  # fmt: skip
        self.assertIsNone(draft.customer.customer_id)
        self.assertEqual(draft.customer.name, "Muster GmbH")

    def test_texts_are_cleaned_and_cut_numbers_are_checked(self) -> None:
        long = "A" * 5000
        draft = self.parse(
            event_name="Fest\x00\x07 mit\nUmbruch" + long,
            positions=[
                {"description": "B" * 900, "quantity": "NaN", "unit_price": "1e999"},
                {"description": "Gut", "quantity": "2", "unit_price": "10,00", "tax_rate": 19},
                {"description": "Float", "quantity": 1.5, "unit_price": 3.3},
                {"description": "", "quantity": "1", "unit_price": "1,00"},
            ],
        )
        self.assertEqual(len(draft.invoice.event_name), 200)
        self.assertNotIn("\x00", draft.invoice.event_name)
        self.assertEqual(len(draft.lines[0].title), 200)
        self.assertIn(draft.lines[0].quantity, (Decimal("0"), Decimal("1")))
        self.assertEqual(draft.lines[0].unit_price, Decimal("0"))  # unusable → empty, the checks ask
        self.assertEqual(draft.lines[2].quantity, Decimal("1.50"))
        self.assertEqual(draft.lines[2].unit_price, Decimal("3.30"))
        self.assertEqual(len(draft.lines), 3)  # the one without a text is left out

    def test_not_an_object_is_refused_and_the_number_of_positions_is_capped(self) -> None:
        with self.assertRaises(ValueError):
            legacy_invoices.parse_answer("Ich kann das nicht.")
        many = [{"description": f"P{i}", "quantity": "1", "unit_price": "1,00", "tax_rate": 19} for i in range(300)]
        self.assertEqual(len(self.parse(positions=many).lines), 100)

    def test_gross_prices_become_net(self) -> None:
        draft = self.parse(
            prices_include_tax=True,
            positions=[{"description": "Licht", "quantity": "1", "unit_price": "119,00", "tax_rate": 19}],
        )
        self.assertEqual(draft.lines[0].unit_price, Decimal("100.00"))

    def test_decimal_of_never_takes_nan_or_huge_numbers(self) -> None:
        for bad in ("NaN", "Infinity", "-Infinity", "1e400", "abc", "", None, True, "1" * 40):
            self.assertIsNone(decimal_of(bad), bad)
        self.assertEqual(decimal_of(" 12.345 ", places=2), Decimal("12.35"))
        self.assertEqual(decimal_of(1.1, places=2), Decimal("1.10"))


# --- The service ------------------------------------------------------------------------------------------------------


class ImportCase(FilesMixin, RentalarsTestCase):
    """Common set-up: a company that can invoice, a user of the import, no AI."""

    def setUp(self) -> None:
        super().setUp()
        ready_for_invoices()
        self.user = power_user()
        self.rights = ALL_RIGHTS

    def batch_of(self, *contents: bytes, user: Any = None) -> LegacyImportBatch:
        files = [upload(f"re-{index}.pdf", content) for index, content in enumerate(contents)]
        batch, rejected = legacy_import.add_files(files, user=user or self.user)
        self.assertEqual(rejected, [])
        assert batch is not None
        legacy_import.start_reading(batch, user=user or self.user)
        return batch

    def items(self, batch: LegacyImportBatch) -> list[LegacyImportItem]:
        return list(batch.items.order_by("position"))

    def take(self, *items: LegacyImportItem) -> list[legacy_import.Outcome]:
        fresh = [LegacyImportItem.objects.get(pk=item.pk) for item in items]
        return legacy_import.confirm(fresh, user=self.user, rights=self.rights)


class UploadTests(ImportCase):
    """What an upload accepts and refuses."""

    def test_pdfs_are_kept_and_a_text_is_not_a_pdf(self) -> None:
        text = SimpleUploadedFile("brief.pdf", b"nur Text", "application/pdf")
        other = SimpleUploadedFile("tabelle.xlsx", b"%PDF-1.4 vorgetaeuscht", "application/pdf")
        empty = SimpleUploadedFile("leer.pdf", b"", "application/pdf")
        good = upload("gut.pdf")
        batch, rejected = legacy_import.add_files([text, other, empty, good], user=self.user)
        self.assertEqual([entry.name for entry in rejected], ["brief.pdf", "tabelle.xlsx", "leer.pdf"])
        assert batch is not None
        self.assertEqual(batch.items.count(), 1)
        item = batch.items.get()
        self.assertEqual((item.state, item.original_name), (ItemState.UPLOADED, "gut.pdf"))
        self.assertTrue(legacy_import.stored_path(item).is_file())
        self.assertRegex(item.stored_name, r"^[0-9a-f]{32}\.pdf$")  # no name of the client reaches the disk

    def test_too_many_and_too_large(self) -> None:
        old = legacy_import.MAX_FILE_BYTES
        legacy_import.MAX_FILE_BYTES = 100
        self.addCleanup(setattr, legacy_import, "MAX_FILE_BYTES", old)
        batch, rejected = legacy_import.add_files([upload()], user=self.user)
        self.assertIsNone(batch)
        self.assertEqual(len(rejected), 1)
        legacy_import.MAX_FILE_BYTES = old
        old = legacy_import.MAX_FILES
        legacy_import.MAX_FILES = 2
        self.addCleanup(setattr, legacy_import, "MAX_FILES", old)
        batch, rejected = legacy_import.add_files(
            [
                upload("a.pdf", invoice_pdf(number="1")),
                upload("b.pdf", invoice_pdf(number="2")),
                upload("c.pdf", invoice_pdf(number="3")),
            ],
            user=self.user,
        )
        assert batch is not None
        self.assertEqual((batch.items.count(), len(rejected)), (2, 1))

    def test_the_same_file_twice_in_one_upload(self) -> None:
        batch, _rejected = legacy_import.add_files([upload("a.pdf"), upload("b.pdf")], user=self.user)
        assert batch is not None
        states = [item.state for item in self.items(batch)]
        self.assertEqual(states, [ItemState.UPLOADED, ItemState.DUPLICATE])
        self.assertEqual(self.items(batch)[1].stored_name, "")  # a duplicate is not kept

    def test_old_files_that_were_never_taken_over_are_dropped(self) -> None:
        batch = self.batch_of(invoice_pdf())
        item = self.items(batch)[0]
        path = legacy_import.stored_path(item)
        LegacyImportBatch.objects.filter(pk=batch.pk).update(created_at=batch.created_at.replace(year=2020))
        self.assertEqual(legacy_import.delete_old_files(), 1)
        self.assertFalse(path.exists())
        item.refresh_from_db()
        self.assertEqual(item.state, ItemState.SKIPPED)

    def test_a_scan_gives_an_empty_proposal_to_type_in(self) -> None:
        batch = self.batch_of(scanned_pdf())
        item = self.items(batch)[0]
        self.assertEqual(item.state, ItemState.READ)
        self.assertEqual(legacy_import.draft_of(item).lines, [])
        self.assertTrue(item.message)


class ReadingTests(ImportCase):
    """Reading without AI: the patterns; customer matching never creates anything."""

    def test_reading_by_patterns_creates_nothing(self) -> None:
        before = (Customer.objects.count(), Project.objects.count(), Document.objects.count())
        batch = self.batch_of(invoice_pdf())
        item = self.items(batch)[0]
        self.assertEqual((item.state, item.source, item.invoice_number), (ItemState.READ, "text", "2023-0042"))
        self.assertEqual((Customer.objects.count(), Project.objects.count(), Document.objects.count()), before)
        draft = legacy_import.draft_of(item)
        self.assertIsNone(draft.customer.customer_id)  # a new customer is proposed, not made

    def test_an_existing_customer_is_proposed_by_the_vat_id(self) -> None:
        customer = make_customer("Stadtwerke Beispielburg")
        customer.vat_id = "DE123456789"
        customer.save()
        draft = legacy_import.draft_of(self.items(self.batch_of(invoice_pdf()))[0])
        self.assertEqual(draft.customer.customer_id, customer.pk)


class CheckTests(ImportCase):
    """Plausibility checks are warnings, what makes the result wrong is an error."""

    def report(self, draft: Draft | None = None, item: LegacyImportItem | None = None) -> legacy_import.Report:
        item = item or self.items(self.batch_of(invoice_pdf()))[0]
        return legacy_import.check(draft or legacy_import.draft_of(item), item, rights=self.rights)

    def test_a_good_invoice_has_neither_errors_nor_warnings(self) -> None:
        report = self.report()
        self.assertEqual(
            ([issue.message for issue in report.errors], [issue.message for issue in report.warnings]), ([], [])
        )

    def test_the_sum_of_the_positions_against_the_totals(self) -> None:
        item = self.items(self.batch_of(invoice_pdf(wrong_total="700.00")))[0]
        report = legacy_import.check(legacy_import.draft_of(item), item, rights=self.rights)
        self.assertTrue(report.ok)  # a warning only
        self.assertIn("total_net", [issue.key for issue in report.warnings])

    def test_tax_that_does_not_fit_the_rate_of_the_positions(self) -> None:
        draft = legacy_import.draft_of(self.items(self.batch_of(invoice_pdf()))[0])
        draft.totals.tax = Decimal("99.00")
        report = legacy_import.check(draft, rights=self.rights)
        self.assertIn("total_tax", [issue.key for issue in report.warnings])

    def test_the_printed_amount_against_quantity_times_price(self) -> None:
        draft = legacy_import.draft_of(self.items(self.batch_of(invoice_pdf()))[0])
        draft.lines[0].amount = Decimal("150.00")
        self.assertIn(
            "lines.0.amount", [issue.key for issue in legacy_import.check(draft, rights=self.rights).warnings]
        )

    def test_errors(self) -> None:
        draft = legacy_import.draft_of(self.items(self.batch_of(invoice_pdf()))[0])
        draft.invoice.number = ""
        draft.invoice.date = None
        draft.lines[0].tax_percent = Decimal("17")
        draft.lines[1].tax_percent = None
        draft.lines[2].quantity = Decimal("0")
        draft.customer.name = ""
        keys = {issue.key for issue in legacy_import.check(draft, rights=self.rights).errors}
        self.assertEqual(keys, {"number", "date", "lines.0.tax", "lines.1.tax", "lines.2.quantity", "customer_name"})

    def test_a_date_in_the_future_other_currency_and_reversed_period(self) -> None:
        draft = legacy_import.draft_of(self.items(self.batch_of(invoice_pdf()))[0])
        draft.invoice.date = draft.invoice.date.replace(year=2030)
        draft.invoice.currency = "USD"
        draft.invoice.service_end = draft.invoice.service_start.replace(day=1)
        keys = {issue.key for issue in legacy_import.check(draft, rights=self.rights).errors}
        self.assertEqual(keys, {"date", "currency", "service_end"})

    def test_no_positions_at_all(self) -> None:
        draft = legacy_import.draft_of(self.items(self.batch_of(scanned_pdf()))[0])
        draft.invoice.number, draft.customer.name = "X-1", "Muster"
        draft.invoice.date = draft.invoice.date or __import__("datetime").date(2023, 1, 1)
        self.assertIn("lines", [issue.key for issue in legacy_import.check(draft, rights=self.rights).errors])

    def test_the_number_range_of_the_live_invoices(self) -> None:
        number_range = NumberRange.objects.get(key=NumberRangeKey.INVOICE)
        number_range.next_value, number_range.current_year = 5, 2027
        number_range.save()
        self.assertTrue(legacy_import.range_collision("RE-2027-0005"))
        self.assertTrue(legacy_import.range_collision("RE-2027-0042"))
        self.assertFalse(legacy_import.range_collision("RE-2027-0004"))  # behind the counter: can never come again
        self.assertFalse(legacy_import.range_collision("RE-2026-0900"))  # an earlier year restarts at 1
        self.assertTrue(legacy_import.range_collision("RE-2028-0001"))  # a later year will use it
        self.assertFalse(legacy_import.range_collision("2023-0042"))
        self.assertFalse(legacy_import.range_collision("ALT-RE-2027-0100"))
        draft = legacy_import.draft_of(self.items(self.batch_of(invoice_pdf()))[0])
        draft.invoice.number = "RE-2027-0100"
        self.assertEqual([issue.key for issue in legacy_import.check(draft, rights=self.rights).errors], ["number"])

    def test_a_customer_with_the_same_name_must_be_chosen_or_confirmed(self) -> None:
        make_customer("Beispielburg Stadtwerke AG")
        draft = legacy_import.draft_of(self.items(self.batch_of(invoice_pdf()))[0])
        draft.customer.customer_id = None
        self.assertEqual([issue.key for issue in legacy_import.check(draft, rights=self.rights).errors], ["customer"])
        draft.customer.allow_duplicate = True
        self.assertTrue(legacy_import.check(draft, rights=self.rights).ok)


class TakeOverTests(ImportCase):
    """Confirming: what is created, and what is not."""

    def setUp(self) -> None:
        super().setUp()
        self.office = make_user("bea")
        self.numbers = {
            number_range.key: (number_range.next_value, number_range.current_year)
            for number_range in NumberRange.objects.all()
        }

    def test_a_closed_project_with_the_historic_invoice(self) -> None:
        batch = self.batch_of(invoice_pdf())
        (item,) = self.items(batch)
        (outcome,) = self.take(item)
        self.assertTrue(outcome.ok, outcome.errors)
        project, customer, (document,) = outcome.project, outcome.customer, outcome.documents
        self.assertEqual(
            (project.status, project.name, project.number), (ProjectStatus.CLOSED, "Stadtfest 2023", "ALT-2023-0001")
        )
        self.assertEqual(project.invoice_status, InvoiceMark.ISSUED)
        self.assertEqual(days_of(project), ("2023-06-10", "2023-06-12"))
        self.assertEqual(
            (customer.name, customer.vat_id, customer.postal_code),
            ("Beispielburg Stadtwerke AG", "DE123456789", "54321"),
        )
        self.assertTrue(outcome.customer_created)
        lines = list(project.material_lines.order_by("position"))
        self.assertEqual(
            next((line.title, line.quantity, line.unit_price, line.tax_rate.rate) for line in lines),
            ("LED Scheinwerfer PAR 64", Decimal("8"), Decimal("25.00"), Decimal("19.00")),
        )
        # "Techniker Aufbau, 6 Std" is personnel: a crew line billed by the hour, not a material line.
        self.assertEqual(len(lines), 2)
        (crew,) = project.crew_lines.all()
        self.assertEqual(
            (crew.title, crew.billing, crew.planned_hours, crew.unit_price, crew.person),
            ("Techniker Aufbau", "plan", Decimal("6.00"), Decimal("55.00"), None),
        )
        self.assertEqual(
            (document.number, str(document.issued_on), document.net_total, document.gross_total, document.kind),
            ("2023-0042", "2023-06-15", Decimal("710.00"), Decimal("844.90"), "invoice"),
        )
        self.assertEqual(document.project, project)
        self.assertTrue(document.is_historic)
        self.assertFalse(document.is_bookable)
        with document.file.open("rb") as stored:
            self.assertEqual(stored.read(), invoice_pdf())  # the original PDF
        self.assertEqual(len(document.sha256), 64)
        item.refresh_from_db()
        self.assertEqual(
            (item.state, item.project, item.document, item.imported_by),
            (ItemState.IMPORTED, project, document, self.user),
        )
        self.assertEqual(item.stored_name, "")  # the pending copy is gone
        self.assertIn("Importiert aus Rechnung 2023-0042", project.notes)
        self.assertIn(self.user.get_username(), project.notes)
        self.assertIn("Importiert aus Rechnung 2023-0042", customer.note)
        self.assertEqual(AuditLogEntry.objects.filter(event="project.legacy_imported").count(), 1)

    def test_nothing_is_sent_made_reserved_or_numbered(self) -> None:
        recipient = make_user("empfang")
        Automation(
            name="Info",
            trigger=Trigger.PROJECT_STATUS,
            action=Action.NOTIFY,
            status=ProjectStatus.CLOSED,
            recipient=Recipient.USER,
            user=recipient,
        ).save()
        hook = Webhook.objects.create(
            url="https://erp.example.de/hook", description="ERP", events=["project.created", "document.created"]
        )
        batch = self.batch_of(invoice_pdf())
        with self.captureOnCommitCallbacks(execute=True):
            (outcome,) = self.take(*self.items(batch))
        self.assertTrue(outcome.ok, outcome.errors)
        self.assertEqual(mail.outbox, [])
        # Only the note to the uploader that the reading task is done – nothing of the project or the invoice.
        self.assertEqual(list(Notification.objects.values_list("kind", flat=True)), ["job_finished"])
        self.assertEqual(AutomationRun.objects.count(), 0)
        self.assertEqual(WebhookDelivery.objects.filter(webhook=hook).count(), 0)
        after = {
            number_range.key: (number_range.next_value, number_range.current_year)
            for number_range in NumberRange.objects.all()
        }
        # The ranges of invoices, projects and documents were not touched (a new customer takes its customer number).
        for key in ("invoice", "project", "document", "offer", "order_confirmation", "delivery_note", "crew_sheet"):
            self.assertEqual(after.get(key), self.numbers.get(key), key)
        self.assertIsNone(outcome.documents[0].sent_at)
        # A project that is made by hand afterwards still notifies: the switch is off again.
        from tests.helpers import make_project

        with self.captureOnCommitCallbacks(execute=True):
            make_project("Danach", status=ProjectStatus.CLOSED, customer=outcome.customer)
        self.assertEqual(Notification.objects.filter(kind="automation").count(), 1)

    def test_idempotence_the_same_pdf_and_the_same_invoice_number(self) -> None:
        self.take(*self.items(self.batch_of(invoice_pdf())))
        again, _rejected = legacy_import.add_files([upload()], user=self.user)
        assert again is not None
        (twin,) = self.items(again)
        self.assertEqual(twin.state, ItemState.DUPLICATE)
        self.assertIn("2023-0042", twin.message)
        # Another file with the same number: blocked by the checks, nothing is created.
        batch = self.batch_of(invoice_pdf(positions=(("Etwas anderes", "1", "Stk", "10.00"),)))
        (other,) = self.items(batch)
        (outcome,) = self.take(other)
        self.assertFalse(outcome.ok)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Document.objects.count(), 1)

    def test_an_existing_customer_is_used_and_not_changed(self) -> None:
        customer = make_customer("Stadtwerke Beispielburg")
        customer.vat_id = "DE123456789"
        customer.save()
        (item,) = self.items(self.batch_of(invoice_pdf()))
        (outcome,) = self.take(item)
        self.assertEqual((outcome.customer, outcome.customer_created), (customer, False))
        self.assertEqual(Customer.objects.count(), 2)  # the one of the company set-up and this one: none new
        customer.refresh_from_db()
        self.assertEqual(customer.postal_code, "")  # not overwritten with data from the invoice

    def test_the_second_project_number_and_partial_confirmation(self) -> None:
        batch = self.batch_of(invoice_pdf(), invoice_pdf(number="2023-0043", date="20.06.2023", event="Messe 2023"))
        first, second = self.items(batch)
        (outcome,) = self.take(second)
        self.assertEqual(outcome.project.number, "ALT-2023-0001")
        self.assertEqual(LegacyImportItem.objects.get(pk=first.pk).state, ItemState.READ)  # still waiting
        (later,) = self.take(first)
        self.assertEqual(later.project.number, "ALT-2023-0002")
        self.assertEqual(later.customer, outcome.customer)  # found again by the VAT ID… the second time

    def test_two_invoices_one_project(self) -> None:
        batch = self.batch_of(
            invoice_pdf(),
            invoice_pdf(
                number="2023-0043", date="20.06.2023", event="Stadtfest 2023 (Abbau)", period="13.06.2023 - 14.06.2023"
            ),
        )
        first, second = self.items(batch)
        legacy_import.save_draft(second, legacy_import.draft_of(second), merge_into=first)
        outcomes = self.take(first, second)
        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        self.assertTrue(outcome.ok, outcome.errors)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Document.objects.count(), 2)
        self.assertEqual((outcome.project.material_lines.count(), outcome.project.crew_lines.count()), (4, 2))
        self.assertEqual(
            days_of(outcome.project),
            ("2023-06-10", "2023-06-14"),
        )
        self.assertEqual(sorted(document.number for document in outcome.documents), ["2023-0042", "2023-0043"])

    def test_a_group_that_fails_does_not_stop_the_others(self) -> None:
        batch = self.batch_of(invoice_pdf(), invoice_pdf(number="2023-0043", date="20.06.2023"))
        first, second = self.items(batch)
        draft = legacy_import.draft_of(first)
        draft.invoice.number = ""
        legacy_import.save_draft(first, draft)
        outcomes = self.take(first, second)
        self.assertEqual([outcome.ok for outcome in outcomes], [False, True])
        self.assertEqual(Project.objects.count(), 1)

    def test_a_proposal_changed_after_the_confirmation_page_is_not_taken_over(self) -> None:
        (item,) = self.items(self.batch_of(invoice_pdf()))
        seen = legacy_import.fingerprint(item)
        draft = legacy_import.draft_of(item)
        draft.lines[0].unit_price = Decimal("1.00")
        legacy_import.save_draft(item, draft)
        (outcome,) = legacy_import.confirm([item], user=self.user, rights=self.rights, fingerprints={item.pk: seen})
        self.assertFalse(outcome.ok)
        self.assertEqual(Project.objects.count(), 0)

    def test_paid_and_free_text_lines_and_a_product(self) -> None:
        from tests.helpers import make_stock

        product = make_stock("L-0001", 8, "LED Scheinwerfer PAR 64", price="25.00")
        (item,) = self.items(self.batch_of(invoice_pdf()))
        draft = legacy_import.draft_of(item)
        self.assertEqual(draft.lines[0].product_id, product.pk)  # the same name: chosen beforehand
        draft.invoice.paid, draft.invoice.paid_on = True, draft.invoice.date
        draft.lines.append(Line(title="Vielen Dank für Ihren Auftrag.", is_text=True))
        legacy_import.save_draft(item, draft)
        (outcome,) = self.take(item)
        self.assertTrue(outcome.ok, outcome.errors)
        lines = list(outcome.project.material_lines.order_by("position"))
        self.assertEqual(lines[0].product, product)
        self.assertTrue(
            lines[2].is_text
        )  # the personnel position is a crew line, the text line the third material line
        item.refresh_from_db()
        self.assertTrue(item.paid)
        self.assertEqual(item.paid_on, draft.invoice.date)

    def test_a_user_without_the_right_creates_nothing(self) -> None:
        from django.core.exceptions import PermissionDenied

        (item,) = self.items(self.batch_of(invoice_pdf()))
        from rentalars.accounts.rights import rights_of

        with self.assertRaises(PermissionDenied):
            legacy_import.confirm([item], user=self.office, rights=rights_of(self.office))
        self.assertEqual(Project.objects.count(), 0)


class UndoTests(ImportCase):
    """An import can be taken back for a week, while nothing was changed on what it made."""

    def made(self) -> tuple[LegacyImportBatch, legacy_import.Outcome]:
        batch = self.batch_of(invoice_pdf())
        (outcome,) = self.take(*self.items(batch))
        return batch, outcome

    def test_undo_removes_what_the_import_made(self) -> None:
        batch, _outcome = self.made()
        self.assertEqual(legacy_import.undo_problems(batch, user=self.user, rights=self.rights), [])
        self.assertEqual(legacy_import.undo(batch, user=self.user, rights=self.rights), 1)
        self.assertEqual(
            (Project.objects.count(), Document.objects.count(), Customer.objects.count()), (0, 0, 1)
        )  # the company's set-up customer stays
        (item,) = self.items(batch)
        self.assertEqual(item.state, ItemState.UNDONE)
        # The PDF can be imported again.
        again, _rejected = legacy_import.add_files([upload()], user=self.user)
        assert again is not None
        self.assertEqual(self.items(again)[0].state, ItemState.UPLOADED)

    def test_not_after_a_change(self) -> None:
        batch, outcome = self.made()
        project = Project.objects.get(pk=outcome.project.pk)
        project.venue = "Geändert"
        project.save()
        self.assertTrue(legacy_import.undo_problems(batch, user=self.user, rights=self.rights))
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            legacy_import.undo(batch, user=self.user, rights=self.rights)
        self.assertEqual(Project.objects.count(), 1)

    def test_not_after_a_week(self) -> None:
        batch, _outcome = self.made()
        LegacyImportItem.objects.filter(batch=batch).update(imported_at=batch.created_at.replace(year=2020))
        self.assertTrue(legacy_import.undo_problems(batch, user=self.user, rights=self.rights))

    def test_not_when_the_customer_got_other_work(self) -> None:
        from tests.helpers import make_project

        batch, outcome = self.made()
        make_project("Neu", customer=outcome.customer)
        self.assertTrue(legacy_import.undo_problems(batch, user=self.user, rights=self.rights))

    def test_not_when_the_invoice_was_sent(self) -> None:
        import datetime

        batch, outcome = self.made()
        Document.objects.filter(pk=outcome.documents[0].pk).update(
            sent_at=datetime.datetime(2027, 3, 1, tzinfo=datetime.UTC)
        )
        self.assertTrue(legacy_import.undo_problems(batch, user=self.user, rights=self.rights))


# --- The pages --------------------------------------------------------------------------------------------------------


class PageTests(AIMixin, FilesMixin, UiTestCase):
    """The way a person does it: upload, check, confirm."""

    def setUp(self) -> None:
        super().setUp()
        ready_for_invoices()
        self.url = reverse("projects:legacy")

    def upload(self, *contents: bytes, client: Any = None) -> Any:
        files = [upload(f"re-{index}.pdf", content) for index, content in enumerate(contents)]
        return (client or self.client).post(self.url, {"invoices": files}, follow=True)

    def batch_page(self, response: Any) -> tuple[str, LegacyImportBatch]:
        return self.assert_ok(response), LegacyImportBatch.objects.latest("pk")

    def form(self, response: Any, **changes: Any) -> dict[str, Any]:
        """The preview form as a browser would send it, with some values changed."""
        for candidate in forms_of(response):
            if any(key.endswith("lines-count") for key in candidate.data):
                data = {key: value for key, value in candidate.data.items() if key != "csrfmiddlewaretoken"}
                data.update(changes)
                return data
        raise AssertionError("No preview form on the page.")

    def test_the_overview_and_the_tab(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Altprojekte importieren", page)
        self.assertIn('name="invoices"', page)
        self.assertIn("Noch keine Altprojekte übernommen.", page)
        self.assertIn(
            self.url, self.assert_ok(self.client.get(reverse("documents:outgoing")))
        )  # the tab of Buchhaltung

    def test_upload_reads_and_shows_a_preview_without_creating_anything(self) -> None:
        before = (Project.objects.count(), Customer.objects.count(), Document.objects.count())
        page, batch = self.batch_page(self.upload(invoice_pdf()))
        item = batch.items.get()
        self.assertEqual(item.state, ItemState.READ)
        self.assertIn("per Muster gelesen", page)
        self.assertIn('value="2023-0042"', page)
        self.assertIn("Beispielburg Stadtwerke AG", page)
        self.assertIn("LED Scheinwerfer PAR 64", page)
        self.assertEqual((Project.objects.count(), Customer.objects.count(), Document.objects.count()), before)

    def test_the_whole_way_with_ai_check_correct_confirm(self) -> None:
        secret = make_customer("Geheimkunde Nord GmbH")
        self.reading_on(answer_of())
        page, batch = self.batch_page(self.upload(invoice_pdf()))
        self.assertIn("von der KI gelesen" if "von der KI gelesen" in page else "mit KI gelesen", page)
        # Only the text of the invoice went to the model – nothing from the customer master data.
        (chat,) = self.fake.chats
        sent = json.dumps(chat)
        self.assertIn("Rechnungsnummer: 2023-0042", sent)
        self.assertNotIn("Geheimkunde", sent)
        call = AICall.objects.get()
        self.assertEqual((call.use, call.ok), ("invoice", True))
        item = batch.items.get()
        prefix = f"i{item.pk}-"
        response = self.client.get(reverse("projects:legacy_batch", args=[batch.pk]))
        data = self.form(response)
        self.assertEqual(data[prefix + "customer_vat_id"], "DE123456789")
        self.assertEqual(data[prefix + "venue"], "Marktplatz")
        # Review without ticking anything is refused.
        refused = self.client.post(response.request["PATH_INFO"], {**data, "action": "review"})
        self.assertIn("Hake die Rechnungen an", self.assert_ok(refused))
        # Correct the event name and the first price, then continue: the confirmation shows what will be created.
        data.update(
            {
                prefix + "event_name": "Stadtfest 2023 (korrigiert)",
                prefix + "l0-unit_price": "26,00",
                "take": str(item.pk),
            }
        )
        shown = self.client.post(response.request["PATH_INFO"], {**data, "action": "review"})
        text = self.assert_ok(shown)
        self.assertIn("Genau das wird angelegt", text)
        self.assertIn("Stadtfest 2023 (korrigiert)", text)
        self.assertIn("wird angelegt", text)  # the customer
        self.assertEqual(Project.objects.count(), 0)  # still nothing
        confirm = form_data(shown, containing=f"fp-{item.pk}")
        done = self.client.post(response.request["PATH_INFO"], {**confirm, "action": "confirm"}, follow=True)
        text = self.assert_ok(done)
        self.assertIn("wurde übernommen", text)
        project = Project.objects.get()
        self.assertEqual((project.name, project.status), ("Stadtfest 2023 (korrigiert)", ProjectStatus.CLOSED))
        self.assertEqual(project.material_lines.order_by("position").first().unit_price, Decimal("26.00"))
        self.assertEqual(Document.objects.get().number, "2023-0042")
        self.assertIn(project.number, text)
        self.assertIsNotNone(secret.pk)

    def test_what_blocks_is_marked_and_nothing_is_created(self) -> None:
        _page, batch = self.batch_page(self.upload(invoice_pdf()))
        item = batch.items.get()
        prefix = f"i{item.pk}-"
        path = reverse("projects:legacy_batch", args=[batch.pk])
        data = self.form(self.client.get(path))
        data.update({prefix + "number": "", prefix + "l1-tax": "17", "take": str(item.pk)})
        response = self.client.post(path, {**data, "action": "review"})
        text = self.assert_ok(response)
        self.assertIn("Gib die Rechnungsnummer ein.", text)
        self.assertIn("Steuersatz von 17", text)
        self.assertIn(
            "kann man noch nicht übernehmen"
            if "kann man noch nicht übernehmen" in text
            else "Korrigiere, was unten markiert ist",
            text,
        )
        self.assertEqual(Project.objects.count(), 0)

    def test_a_number_that_cannot_be_read_is_kept_as_typed(self) -> None:
        _page, batch = self.batch_page(self.upload(invoice_pdf()))
        item = batch.items.get()
        path = reverse("projects:legacy_batch", args=[batch.pk])
        data = self.form(self.client.get(path))
        data.update({f"i{item.pk}-l0-unit_price": "viel", f"i{item.pk}-total_net": "abc"})
        text = self.assert_ok(self.client.post(path, {**data, "action": "save"}))
        self.assertIn('value="viel"', text)
        self.assertIn("Das ist keine Zahl.", text)

    def test_another_position_and_removing_one(self) -> None:
        _page, batch = self.batch_page(self.upload(invoice_pdf()))
        item = batch.items.get()
        path = reverse("projects:legacy_batch", args=[batch.pk])
        data = self.form(self.client.get(path))
        self.client.post(path, {**data, "action": f"more-{item.pk}"})
        item.refresh_from_db()
        self.assertEqual(len(legacy_import.draft_of(item).lines), 4)
        data = self.form(self.client.get(path))
        data[f"i{item.pk}-l3-remove"] = "on"
        data[f"i{item.pk}-l0-remove"] = "on"
        self.client.post(path, {**data, "action": "save"})
        item.refresh_from_db()
        self.assertEqual(
            [line.title for line in legacy_import.draft_of(item).lines], ["Mischpult Behringer X32", "Techniker Aufbau"]
        )

    def test_two_invoices_skip_one_and_join(self) -> None:
        _page, batch = self.batch_page(
            self.upload(
                invoice_pdf(),
                invoice_pdf(number="2023-0043", date="20.06.2023"),
                invoice_pdf(number="2023-0044", date="21.06.2023"),
            )
        )
        first, second, third = self.batch_items(batch)
        path = reverse("projects:legacy_batch", args=[batch.pk])
        data = self.form(self.client.get(path))
        data[f"i{second.pk}-merge"] = str(first.pk)
        data["take"] = [str(first.pk), str(second.pk)]
        self.client.post(path, {**data, "action": f"skip-{third.pk}"})
        self.assertEqual(LegacyImportItem.objects.get(pk=third.pk).state, ItemState.SKIPPED)
        data = self.form(self.client.get(path))
        data[f"i{second.pk}-merge"] = str(first.pk)
        data["take"] = [str(first.pk), str(second.pk)]
        shown = self.client.post(path, {**data, "action": "review"})
        text = self.assert_ok(shown)
        self.assertEqual(text.count('<h2 id="plan-'), 1)  # one project for both
        self.assertIn("2023-0043", text)
        confirm = form_data(shown, containing=f"fp-{first.pk}")
        self.client.post(path, {**confirm, "action": "confirm"})
        self.assertEqual((Project.objects.count(), Document.objects.count()), (1, 2))
        self.assertFalse(Path(self.data_dir / "legacy-invoices" / third.stored_name).exists())

    def batch_items(self, batch: LegacyImportBatch) -> list[LegacyImportItem]:
        return list(batch.items.order_by("position"))

    def test_the_original_pdf_for_comparing(self) -> None:
        _page, batch = self.batch_page(self.upload(invoice_pdf()))
        item = batch.items.get()
        response = self.client.get(reverse("projects:legacy_pdf", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), invoice_pdf())

    def test_progress_block_and_stuck_batch(self) -> None:
        with self.settings(JOBS_RUN_INLINE=False), self.captureOnCommitCallbacks(execute=False):
            response = self.client.post(self.url, {"invoices": [upload()]}, follow=True)
        text = self.assert_ok(response)
        batch = LegacyImportBatch.objects.get()
        self.assertEqual(batch.items.get().state, ItemState.UPLOADED)
        self.assertIn("wartet aufs Lesen", text)
        self.assertIn(reverse("projects:legacy_progress", args=[batch.pk]), text)
        progress = self.client.get(reverse("projects:legacy_progress", args=[batch.pk]))
        self.assertEqual(progress.status_code, 200)
        self.assertNotIn("HX-Refresh", progress)  # still running: no reload
        from rentalars.core.jobs import run_job

        run_job(batch.job_id)
        done = self.client.get(reverse("projects:legacy_progress", args=[batch.pk]))
        self.assertEqual(done["HX-Refresh"], "true")
        self.assertEqual(batch.items.get().state, ItemState.READ)

    def test_undo_on_the_page(self) -> None:
        _page, batch = self.batch_page(self.upload(invoice_pdf()))
        item = batch.items.get()
        path = reverse("projects:legacy_batch", args=[batch.pk])
        data = self.form(self.client.get(path))
        data["take"] = str(item.pk)
        shown = self.client.post(path, {**data, "action": "review"})
        self.client.post(path, {**form_data(shown, containing=f"fp-{item.pk}"), "action": "confirm"})
        text = self.assert_ok(self.client.get(path))
        self.assertIn("Import zurücknehmen", text)
        undone = self.client.post(reverse("projects:legacy_undo", args=[batch.pk]), follow=True)
        self.assertIn("zurückgenommen", self.assert_ok(undone))
        self.assertEqual((Project.objects.count(), Document.objects.count()), (0, 0))

    def test_rights(self) -> None:
        nobody = self.browser_for("nils", "Lager")
        writer = self.browser_of(power_user("paula"))
        self.upload(invoice_pdf())
        batch = LegacyImportBatch.objects.get()
        item = batch.items.get()
        urls = [
            ("get", self.url),
            ("get", reverse("projects:legacy_batch", args=[batch.pk])),
            ("get", reverse("projects:legacy_progress", args=[batch.pk])),
            ("get", reverse("projects:legacy_pdf", args=[item.pk])),
            ("post", self.url),
            ("post", reverse("projects:legacy_batch", args=[batch.pk])),
            ("post", reverse("projects:legacy_undo", args=[batch.pk])),
        ]
        for method, url in urls:
            self.assertEqual(getattr(nobody, method)(url).status_code, 403, url)
        self.assertEqual(writer.get(self.url).status_code, 200)
        self.assertEqual(writer.get(reverse("projects:legacy_batch", args=[batch.pk])).status_code, 200)
        # A reader of the projects without the price right may not use it either.
        reader_role = Role.objects.create(name="Leser", module_levels={Module.PROJECTS: int(Level.WRITE)})
        reader = make_user("rita")
        reader.roles.add(reader_role)
        self.assertEqual(self.browser_of(reader).get(self.url).status_code, 403)


# --- Accounting: what is left out, what is refused -------------------------------------------------------------------


class AccountingTests(ImportCase):
    """The historic invoice is a record: no DATEV (unless asked), no Lexware, no cancellation."""

    def setUp(self) -> None:
        super().setUp()
        from rentalars.documents.models import AccountingSettings

        accounting = AccountingSettings.load()
        accounting.datev_consultant_number, accounting.datev_client_number = 29098, 55003
        accounting.save()
        (item,) = self.items(self.batch_of(invoice_pdf(date="15.02.2027", number="2027-ALT-1")))
        (self.outcome,) = self.take(item)
        self.document = self.outcome.documents[0]

    def test_datev_leaves_it_out_unless_asked(self) -> None:
        import datetime

        from rentalars.documents import datev

        first, last = datetime.date(2027, 2, 1), datetime.date(2027, 2, 28)
        self.assertEqual(list(datev.documents_in(first, last)), [])
        self.assertEqual(list(datev.documents_in(first, last, include_historic=True)), [self.document])
        without = datev.bookings_file(first, last).content.decode("cp1252")
        self.assertNotIn("2027-ALT-1", without)
        included = datev.bookings_file(first, last, include_historic=True).content.decode("cp1252")
        self.assertIn("2027-ALT-1", included)
        self.assertIn("844,90", included)

    def test_datev_pages(self) -> None:
        self.client.force_login(make_user("buchhalter", superuser=True))
        url = reverse("documents:datev_preview")
        period = {"date_from": "2027-02-01", "date_to": "2027-02-28"}
        self.assertNotIn("2027-ALT-1", self.client_get(url, period))
        self.assertIn("2027-ALT-1", self.client_get(url, {**period, "include_historic": "1"}))
        export = reverse("documents:datev_export")
        plain = self.client.get(export, period)
        self.assertEqual(plain.status_code, 200)
        self.assertNotIn(b"2027-ALT-1", plain.content)
        self.assertIn(b"2027-ALT-1", self.client.get(export, {**period, "include_historic": "1"}).content)

    def client_get(self, url: str, data: dict[str, str]) -> str:
        return self.client.get(url, data).content.decode()

    def test_not_handed_over_not_cancelled_not_missing(self) -> None:
        from django.core.exceptions import ValidationError

        from rentalars.documents import outgoing, services

        self.assertFalse(self.document.is_bookable)
        with self.assertRaises(ValidationError):
            services.cancel_invoice(self.document)
        found = outgoing.Filters(lexware=outgoing.LEXWARE_MISSING).apply(outgoing.documents())
        self.assertNotIn(self.document, found)

    def test_the_list_of_outgoing_documents_and_the_project_show_it(self) -> None:
        self.client.force_login(make_user("buch2", superuser=True))
        page = self.client.get(reverse("documents:outgoing")).content.decode()
        self.assertIn("2027-ALT-1", page)
        project_documents = self.client.get(reverse("documents:list", args=[self.outcome.project.number]))
        self.assertEqual(project_documents.status_code, 200)
        self.assertIn("2027-ALT-1", project_documents.content.decode())
        self.assertEqual(self.client.get(reverse("documents:file", args=[self.document.pk])).status_code, 200)


# --- The API ----------------------------------------------------------------------------------------------------------


class ApiTests(AIMixin, FilesMixin, ApiTestCase):
    """Every step through the API (API-002, API-014)."""

    def setUp(self) -> None:
        super().setUp()
        ready_for_invoices()
        self.office = self.client_of(power_user("petra"))

    def upload(self, *contents: bytes, client: Any = None) -> dict[str, Any]:
        files = [upload(f"re-{index}.pdf", content) for index, content in enumerate(contents)]
        response = (client or self.office).post(f"{API}/legacy-imports", {"files": files}, format="multipart")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_the_whole_way(self) -> None:
        body = self.upload(invoice_pdf(), invoice_pdf(number="2023-0043", date="20.06.2023"))
        self.assertEqual((body["counts"]["total"], body["counts"]["read"]), (2, 2))
        self.assertEqual(body["rejected"], [])
        batch_id = body["id"]
        first, second = body["items"]
        self.assertEqual((first["state"], first["source"], first["errors"]), ("read", "text", []))
        self.assertEqual(first["proposal"]["invoice"]["number"], "2023-0042")
        listing = self.office.get(f"{API}/legacy-imports").json()["results"]
        self.assertEqual([entry["id"] for entry in listing], [batch_id])
        detail = self.office.get(f"{API}/legacy-imports/{batch_id}").json()
        self.assertEqual(len(detail["items"]), 2)

        # Correct the first one, join the second to it.
        proposal = dict(first["proposal"])
        proposal["invoice"] = {**proposal["invoice"], "event_name": "Stadtfest (korrigiert)"}
        changed = self.office.put(f"{API}/legacy-imports/{batch_id}/items/{first['id']}", proposal, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["proposal"]["invoice"]["event_name"], "Stadtfest (korrigiert)")
        joined = self.office.put(
            f"{API}/legacy-imports/{batch_id}/items/{second['id']}", {"merge_into": first["id"]}, format="json"
        )
        self.assertEqual(joined.json()["merge_into"], first["id"])

        ids = [first["id"], second["id"]]
        preview = self.office.post(f"{API}/legacy-imports/{batch_id}/preview", {"items": ids}, format="json")
        self.assertEqual(preview.status_code, 200, preview.content)
        (plan,) = preview.json()["plans"]
        self.assertEqual(
            (plan["project"], plan["customer_new"], len(plan["invoices"]), plan["errors"]),
            ("Stadtfest (korrigiert)", True, 2, []),
        )
        self.assertEqual(Project.objects.count(), 0)

        stale = self.office.post(
            f"{API}/legacy-imports/{batch_id}/confirm",
            {"items": ids, "fingerprints": {str(i): "0000" for i in ids}},
            format="json",
        )
        self.assertEqual(stale.status_code, 409, stale.content)
        self.assertEqual(Project.objects.count(), 0)
        missing = self.office.post(
            f"{API}/legacy-imports/{batch_id}/confirm", {"items": ids, "fingerprints": {}}, format="json"
        )
        self.assertEqual(missing.status_code, 400)

        done = self.office.post(
            f"{API}/legacy-imports/{batch_id}/confirm",
            {"items": ids, "fingerprints": plan["fingerprints"]},
            format="json",
        )
        self.assertEqual(done.status_code, 200, done.content)
        (result,) = done.json()["results"]
        self.assertEqual(
            (result["ok"], result["customer_created"], sorted(result["documents"])),
            (True, True, ["2023-0042", "2023-0043"]),
        )
        self.assertTrue(result["project"].startswith("ALT-2023-"))
        self.assertEqual(Project.objects.get().status, ProjectStatus.CLOSED)

        after = self.office.get(f"{API}/legacy-imports/{batch_id}").json()
        self.assertEqual([entry["state"] for entry in after["items"]], ["imported", "imported"])
        self.assertEqual(after["undo_problems"], [])
        undone = self.office.post(f"{API}/legacy-imports/{batch_id}/undo")
        self.assertEqual((undone.status_code, undone.json()), (200, {"invoices": 2}))
        self.assertEqual((Project.objects.count(), Document.objects.count()), (0, 0))
        again = self.office.post(f"{API}/legacy-imports/{batch_id}/undo")
        self.assertEqual(again.status_code, 400)

    def test_skip_read_and_refusals(self) -> None:
        body = self.upload(invoice_pdf(), scanned_pdf())
        batch_id, (first, second) = body["id"], body["items"]
        skipped = self.office.post(f"{API}/legacy-imports/{batch_id}/items/{first['id']}/skip")
        self.assertEqual((skipped.status_code, skipped.json()["state"]), (200, "skipped"))
        self.assertEqual(self.office.post(f"{API}/legacy-imports/{batch_id}/items/{first['id']}/skip").status_code, 400)
        changed = self.office.put(
            f"{API}/legacy-imports/{batch_id}/items/{first['id']}", {"invoice": {}}, format="json"
        )
        self.assertEqual(changed.status_code, 400)  # no longer waiting to be checked
        read = self.office.post(f"{API}/legacy-imports/{batch_id}/read")
        self.assertEqual((read.status_code, read.json()["job"]), (200, None))  # nothing waits to be read
        self.assertEqual(self.office.post(f"{API}/legacy-imports", {}, format="multipart").status_code, 400)
        text = SimpleUploadedFile("x.pdf", b"kein pdf", "application/pdf")
        refused = self.office.post(f"{API}/legacy-imports", {"files": [text]}, format="multipart")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(len(refused.json()["rejected"]), 1)
        # Nothing but known keys, types and lengths get through a change.
        item = second["id"]
        hostile = self.office.put(
            f"{API}/legacy-imports/{batch_id}/items/{item}",
            {
                "customer": {"name": "A" * 999, "customer_id": "1; DROP", "vat_id": "x"},
                "lines": [{"title": "T", "unit_price": "1e999", "quantity": "NaN", "product_id": "x"}],
                "state": "imported",
                "project": 1,
            },
            format="json",
        )
        self.assertEqual(hostile.status_code, 200, hostile.content)
        proposal = hostile.json()["proposal"]
        self.assertEqual(len(proposal["customer"]["name"]), 200)
        self.assertIsNone(proposal["customer"]["customer_id"])
        self.assertEqual(proposal["lines"][0]["unit_price"], "0")
        self.assertEqual(hostile.json()["state"], "read")
        self.assertEqual(
            self.office.put(
                f"{API}/legacy-imports/{batch_id}/items/{item}", {"merge_into": item}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(self.office.get(f"{API}/legacy-imports/999999").status_code, 404)

    def test_rights(self) -> None:
        body = self.upload(invoice_pdf())
        batch_id, (item,) = body["id"], body["items"]

        def client_with(name: str, levels: dict[str, int], special: list[str]) -> Any:
            role = Role.objects.create(name=f"Rolle {name}", module_levels=levels, special_rights=special)
            user = make_user(name)
            user.roles.add(role)
            return self.client_of(user)

        # Without the right to see prices nothing is open; a reader with prices may look, but not change anything.
        nobody = client_with("nils", {Module.PROJECTS: int(Level.WRITE)}, [])
        reader = client_with("lea", {Module.PROJECTS: int(Level.READ)}, [SpecialRight.PRICES])
        calls = [
            ("get", f"{API}/legacy-imports", None),
            ("post", f"{API}/legacy-imports", None),
            ("get", f"{API}/legacy-imports/{batch_id}", None),
            ("put", f"{API}/legacy-imports/{batch_id}/items/{item['id']}", {}),
            ("post", f"{API}/legacy-imports/{batch_id}/items/{item['id']}/skip", None),
            ("post", f"{API}/legacy-imports/{batch_id}/read", None),
            ("post", f"{API}/legacy-imports/{batch_id}/preview", {"items": [item["id"]]}),
            ("post", f"{API}/legacy-imports/{batch_id}/confirm", {"items": [item["id"]], "fingerprints": {}}),
            ("post", f"{API}/legacy-imports/{batch_id}/undo", None),
        ]
        for name, client in (("nobody", nobody), ("reader", reader)):
            for method, url, data in calls:
                response = (
                    getattr(client, method)(url, data, format="json")
                    if data is not None
                    else getattr(client, method)(url)
                )
                allowed = name == "reader" and method == "get"
                self.assertEqual(response.status_code, 200 if allowed else 403, (name, method, url))
        self.assertEqual(Project.objects.count(), 0)

    def test_an_invoice_taken_over_is_a_document_and_datev_can_include_it(self) -> None:
        from rentalars.documents.models import AccountingSettings

        accounting = AccountingSettings.load()
        accounting.datev_consultant_number, accounting.datev_client_number = 29098, 55003
        accounting.save()
        body = self.upload(invoice_pdf(date="15.02.2027", number="2027-ALT-7"))
        batch_id, (item,) = body["id"], body["items"]
        preview = self.office.post(f"{API}/legacy-imports/{batch_id}/preview", {"items": [item["id"]]}, format="json")
        self.office.post(
            f"{API}/legacy-imports/{batch_id}/confirm",
            {"items": [item["id"]], "fingerprints": preview.json()["plans"][0]["fingerprints"]},
            format="json",
        )
        query = "from=2027-02-01&to=2027-02-28"
        self.assertNotIn(
            "2027-ALT-7", self.admin.get(f"{API}/accounting/datev/bookings?{query}").content.decode("cp1252")
        )
        included = self.admin.get(f"{API}/accounting/datev/bookings?{query}&include_historic=true")
        self.assertIn("2027-ALT-7", included.content.decode("cp1252"))
        debitors = self.admin.get(f"{API}/accounting/datev/debitors?{query}&include_historic=true")
        self.assertEqual(debitors.status_code, 200)
        cancel = self.admin.post(f"{API}/documents/{Document.objects.get().pk}/cancel", {}, format="json")
        self.assertEqual(cancel.status_code, 400, cancel.content)
