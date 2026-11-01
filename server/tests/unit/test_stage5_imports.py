# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the imports of products, customers and people and of the full export (IMP-001, IMP-004, IMP-006)."""

from __future__ import annotations

import json
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from rentalars.accounts.rights import Rights
from rentalars.core import export, imports
from rentalars.core.models import BackgroundJob
from rentalars.core.tabular import Table, parse_bool, parse_decimal, resolve_mapping
from rentalars.customers.models import Customer
from rentalars.masterdata.models import Category
from rentalars.personnel.importer import parse_functions, split_name
from rentalars.personnel.models import Person, PersonJobFunction
from rentalars.personnel.services import rate_for, rate_on
from rentalars.products.models import Product, ProductKind
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, category, job_function, make_customer, make_product, make_user

NO_PRICES = Rights(module_levels={"products": 3, "customers": 3, "personnel": 3}, special_rights=frozenset())


def table(rows: list[list[object]]) -> Table:
    return Table(headers=[str(cell) for cell in rows[0]], rows=[list(row) for row in rows[1:]])


def run(key: str, rows: list[list[object]], *, dry_run: bool = False, rights: Rights = ALL_RIGHTS) -> Any:
    """Import ``rows`` (the first one holds the headings) with the import ``key``."""
    kind = imports.get(key)
    data = table(rows)
    return kind.run(data, resolve_mapping(data.headers, {}, kind.fields), dry_run=dry_run, rights=rights)


class CellTests(RentalarsTestCase):
    def test_numbers_and_yes_no(self) -> None:
        self.assertEqual(parse_decimal("1.234,50 €"), Decimal("1234.50"))
        self.assertEqual(parse_decimal("19 %"), Decimal("19.00"))
        self.assertEqual((parse_bool("ja"), parse_bool("nein"), parse_bool("")), (True, False, None))
        with self.assertRaises(ValueError):
            parse_bool("vielleicht")
        self.assertEqual(split_name("Beispiel, Anna"), ("Anna", "Beispiel"))
        self.assertEqual(split_name("Anna Maria Beispiel"), ("Anna Maria", "Beispiel"))
        self.assertEqual(
            parse_functions("Tontechnik: 35,00, Licht;Rigging"),
            [("Tontechnik", Decimal("35.00")), ("Licht", None), ("Rigging", None)],
        )


class ProductImportTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.spots = Category.objects.create(name="Scheinwerfer", parent=category("L"))

    def test_create_update_and_unchanged(self) -> None:
        make_product("L-010", "PAR 64", price="12.00")
        rows = [
            [
                "Art.-Nr.",
                "Name",
                "Kategorie",
                "Preis",
                "Verkaufspreis",
                "Einheit",
                "Steuerart",
                "Mindestbestand",
                "Aktiv",
            ],
            ["L-010", "PAR 64 schwarz", "Scheinwerfer", "14,50", "", "Stk.", "19", "", "ja"],
            ["V-001", "Gaffa-Tape", "", "", "8,90", "Stück", "19 %", "20", "ja"],
            ["k-005", "XLR-Kabel 5 m", "", "2,50", "", "", "", "", ""],
        ]
        dry = run("products", rows, dry_run=True)
        self.assertTrue(dry.ok, dry.errors)
        self.assertEqual((dry.created, dry.updated), (2, 1))
        self.assertFalse(Product.objects.filter(article_number__in=["V-001", "K-005"]).exists())

        report = run("products", rows)
        self.assertTrue(report.ok, report.errors)
        par = Product.objects.get(article_number="L-010")
        self.assertEqual((par.name, par.price, par.category), ("PAR 64 schwarz", Decimal("14.50"), self.spots))
        tape = Product.objects.get(article_number="V-001")
        # The kind comes from the category V (PRD-027): a sale product with its sale price.
        self.assertEqual((tape.kind, tape.sale_price, tape.minimum_stock), (ProductKind.SALE, Decimal("8.90"), 20))
        # ADM-011: the unit the category K presets in an installation.
        self.assertEqual(Product.objects.get(article_number="K-005").unit.name, "Stück (Miete)")
        self.assertEqual(run("products", rows).unchanged, 3)

    def test_errors_stop_everything(self) -> None:
        rows = [
            ["Art.-Nr.", "Name", "Einheit", "Preis"],
            ["L-010", "PAR 64", "Fass", "10"],
            ["X-001", "Unbekannt", "", "10"],
            ["L-011", "", "", "10"],
            ["L-010", "doppelt", "", "10"],
            ["L-012", "ohne Preis", "", ""],
        ]
        report = run("products", rows)
        messages = [str(issue) for issue in report.errors]
        self.assertEqual(len(messages), 5, messages)
        self.assertIn("Zeile 2, Einheit: Es gibt keine Einheit „Fass“.", messages)
        self.assertTrue(any("Zeile 3" in message and "Kürzel X" in message for message in messages))
        self.assertTrue(any("Zeile 5" in message and "Zeile 2" in message for message in messages))
        self.assertFalse(Product.objects.filter(article_number__startswith="L-").exists())

    def test_prices_need_the_price_right(self) -> None:
        report = run("products", [["Art.-Nr.", "Name", "Preis"], ["L-010", "PAR", "10"]], rights=NO_PRICES)
        self.assertEqual(
            [issue.message for issue in report.errors], ["Preise zu importieren braucht das Recht, Preise zu sehen."]
        )


class CustomerImportTests(RentalarsTestCase):
    def test_numbers_decide_and_duplicates_are_noted(self) -> None:
        known = make_customer("Stadtwerke Musterstadt")
        rows = [
            ["Nummer", "Name", "Straße", "PLZ", "Ort", "E-Mail", "Zahlungsziel", "Rabatt", "Ansprechperson"],
            [
                known.number,
                "Stadtwerke Musterstadt GmbH",
                "Markt 1",
                "12345",
                "Musterstadt",
                "",
                "30",
                "5",
                "Eva Licht",
            ],
            ["", "Stadtwerke Musterstadt", "", "", "", "", "", "", ""],
            ["ALT-0815", "Kulturverein", "", "", "Dorf", "kultur@example.de", "", "", ""],
        ]
        report = run("customers", rows)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual((report.created, report.updated), (2, 1))
        known.refresh_from_db()
        self.assertEqual(
            (known.name, known.payment_terms_days, known.default_discount_percent),
            ("Stadtwerke Musterstadt GmbH", 30, Decimal("5.00")),
        )
        self.assertEqual(known.primary_contact.name, "Eva Licht")
        self.assertTrue(Customer.objects.filter(number="ALT-0815", city="Dorf").exists())
        self.assertEqual(len(report.warnings), 1)
        self.assertIn(known.number, report.warnings[0].message)
        self.assertEqual(run("customers", rows[:2]).unchanged, 1)

    def test_discount_needs_the_price_right_and_errors_name_the_row(self) -> None:
        rows = [["Name", "Rabatt"], ["Kulturverein", "5"]]
        self.assertFalse(run("customers", rows, rights=NO_PRICES).ok)
        broken = run("customers", [["Name", "E-Mail", "Zahlungsziel"], ["A", "keine-mail", "bald"]])
        self.assertEqual([issue.row for issue in broken.errors], [2])
        self.assertFalse(Customer.objects.exists())


class PeopleImportTests(RentalarsTestCase):
    def test_people_with_functions_and_rates(self) -> None:
        job_function("Tontechnik", guide="28.00")
        job_function("Licht")
        rows = [
            ["Name", "Art", "Funktionen", "E-Mail"],
            ["Beispiel, Anna", "Freie Kraft", "Tontechnik, Licht: 30,00", "anna@example.de"],
            ["Ben Muster", "fest", "Tontechnik", ""],
        ]
        report = run("people", rows)
        self.assertTrue(report.ok, report.errors)
        anna = Person.objects.get(last_name="Beispiel")
        self.assertEqual((anna.first_name, anna.kind, anna.email), ("Anna", "freelancer", "anna@example.de"))
        self.assertEqual(rate_on(anna, job_function("Licht")), Decimal("30.00"))
        # PER-029: without a rate the function is assigned without own rate; the guide value counts.
        self.assertIsNone(rate_on(anna, job_function("Tontechnik")))
        self.assertEqual(rate_for(anna, job_function("Tontechnik")).hourly, Decimal("28.00"))
        self.assertEqual(Person.objects.get(last_name="Muster").kind, "employee")
        again = run("people", rows)
        self.assertEqual((again.created, again.updated, again.unchanged), (0, 0, 2))
        rows[1][0] = "Beispiel-Neu, Anna"
        renamed = run("people", rows)
        self.assertEqual(renamed.updated, 1)  # found by the e-mail address
        self.assertEqual(PersonJobFunction.objects.filter(person=anna).count(), 2)

    def test_problems(self) -> None:
        job_function("Licht")
        Person.objects.create(first_name="Max", last_name="Muster")
        Person.objects.create(first_name="Max", last_name="Muster")
        rows = [
            ["Vorname", "Nachname", "Funktionen"],
            ["Max", "Muster", ""],
            ["Eva", "Licht", "Licht"],
            ["Paul", "Ton", "Ballett"],
        ]
        report = run("people", rows)
        # PER-029: "Licht" without a rate and without a guide value is no problem any more (row 3).
        self.assertEqual([issue.row for issue in report.errors], [2, 4])
        rates = run("people", [["Name", "Funktionen"], ["Eva Licht", "Licht: 30"]], rights=NO_PRICES)
        self.assertIn("Personalkosten", rates.errors[0].message)
        self.assertFalse(run("people", [["Funktionen"], ["Licht"]]).ok)


class ImportJobTests(RentalarsTestCase):
    """NFA-041: dry run and import as a task in the background."""

    def test_dry_run_keeps_the_file_the_import_removes_it(self) -> None:
        with tempfile.TemporaryDirectory() as folder, override_settings(DATA_DIR=Path(folder)):
            user = make_user("luka", superuser=True)
            upload = SimpleUploadedFile("kunden.csv", b"Name;Ort\nKulturverein;Dorf\n")
            name = imports.store_upload(upload)
            kind = imports.get("customers")
            mapping = {"name": 0, "city": 1}
            dry = imports.start(kind, name, "kunden.csv", mapping, dry_run=True, user=user)
            dry.refresh_from_db()
            self.assertEqual((dry.status, dry.result["report"]["created"]), ("done", 1))
            self.assertTrue(imports.stored_path(name).exists())
            done = imports.start(kind, name, "kunden.csv", mapping, dry_run=False, user=user)
            done.refresh_from_db()
            self.assertEqual(done.message, "Der Import ist abgeschlossen.")
            self.assertFalse(imports.stored_path(name).exists())
            self.assertTrue(Customer.objects.filter(name="Kulturverein").exists())
            self.assertEqual(BackgroundJob.objects.count(), 2)


class InterruptedJobTests(RentalarsTestCase):
    """NFA-041: a task whose process ended without finishing is started once more."""

    def test_restart_once_then_give_up(self) -> None:
        import socket

        from rentalars.core.jobs import recover_interrupted_jobs, run_waiting_jobs
        from rentalars.core.models import JobStatus

        user = make_user("luka", superuser=True)
        dead = {"host": socket.gethostname(), "pid": 2**22 + 12345}
        job = BackgroundJob.objects.create(
            kind="export", title="Export", status=JobStatus.RUNNING, created_by=user, params={"worker": dead}
        )
        alive = BackgroundJob.objects.create(
            kind="export",
            title="läuft",
            status=JobStatus.RUNNING,
            started_at=timezone.now(),
            params={"worker": {"host": socket.gethostname(), "pid": __import__("os").getpid()}},
        )
        self.assertEqual(run_waiting_jobs(), 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.params["attempts"]), ("done", 1))
        alive.refresh_from_db()
        self.assertEqual(alive.status, "running")

        BackgroundJob.objects.filter(pk=job.pk).update(status=JobStatus.RUNNING, params={"attempts": 1, "worker": dead})
        self.assertEqual(recover_interrupted_jobs(), 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.message), ("failed", "Die Aufgabe wurde unterbrochen."))


class FullExportTests(RentalarsTestCase):
    """IMP-006."""

    def test_everything_but_secrets(self) -> None:
        make_user("luka")
        make_customer("Kulturverein")
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "media"
            (media / "projects" / "1").mkdir(parents=True)
            (media / "projects" / "1" / "plan.pdf").write_bytes(b"%PDF-1.4")
            (media / "jobs" / "9").mkdir(parents=True)
            (media / "jobs" / "9" / "alt.zip").write_bytes(b"PK")
            target = Path(folder) / "export.zip"
            with override_settings(MEDIA_ROOT=media):
                counts = export.write_export(target)
            with zipfile.ZipFile(target) as archive:
                names = set(archive.namelist())
                users = json.loads(archive.read("json/accounts.user.json"))
                customers_csv = archive.read("csv/customers.customer.csv").decode("utf-8-sig")
        self.assertIn("LIESMICH.txt", names)
        self.assertIn("dateien/projects/1/plan.pdf", names)
        self.assertNotIn("dateien/jobs/9/alt.zip", names)
        self.assertNotIn("json/sessions.session.json", names)
        self.assertEqual(users[0]["fields"]["username"], "luka")
        self.assertNotIn("password", users[0]["fields"])
        self.assertIn("Kulturverein", customers_csv)
        self.assertEqual(counts["files"], 1)
