# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the imports of products, customers and people, in the background, and the full export (IMP-001, IMP-006, NFA-041)."""

from __future__ import annotations

import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from rentalars.customers.models import Customer
from rentalars.personnel.models import Person
from rentalars.products.models import Product
from tests.api.base import API, ApiTestCase
from tests.helpers import job_function


def csv_file(name: str, text: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class ImportApiTests(ApiTestCase):
    def test_products_customers_people(self) -> None:
        self.assertEqual(self.admin.get(f"{API}/imports/products").json()[0]["key"], "article_number")
        products = self.admin.post(
            f"{API}/imports/products",
            {"file": csv_file("p.csv", "Art.-Nr.;Name;Preis\nL-010;PAR 64;12,00\n"), "dry_run": "false"},
            format="multipart",
        )
        self.assertEqual(products.status_code, 200, products.content)
        self.assertEqual((products.json()["created"], products.json()["mapping"]["price"]), (1, "Preis"))
        self.assertEqual(Product.objects.get(article_number="L-010").price, 12)

        customers = self.admin.post(
            f"{API}/imports/customers",
            {"file": csv_file("k.csv", "Name;Ort\nKulturverein;Dorf\n"), "dry_run": "false"},
            format="multipart",
        )
        self.assertEqual(customers.json()["created"], 1)
        self.assertTrue(Customer.objects.filter(city="Dorf").exists())

        job_function("Licht", guide="25.00")
        people = self.admin.post(
            f"{API}/imports/people",
            {"file": csv_file("l.csv", "Person;Funktionen\nEva Licht;Licht\n"), "dry_run": "false"},
            format="multipart",
        )
        self.assertEqual(people.status_code, 200, people.content)
        self.assertTrue(Person.objects.filter(last_name="Licht").exists())

        broken = self.admin.post(
            f"{API}/imports/people",
            {"file": csv_file("l.csv", "Person;Funktionen\nEva Licht;Ballett\n")},
            format="multipart",
        )
        self.assertEqual(broken.status_code, 400)
        self.assertEqual(broken.json()["errors"][0]["row"], 2)
        self.assert_error(self.admin.get(f"{API}/imports/nothing"), 404, "not_found")
        self.assert_error(
            self.client_for("luka", "Lager").post(
                f"{API}/imports/customers", {"file": csv_file("k.csv", "Name\nX\n")}, format="multipart"
            ),
            403,
            "permission_denied",
        )

    @override_settings(MAX_IMPORT_ROWS_PER_REQUEST=1)
    def test_long_lists_run_in_the_background(self) -> None:
        """NFA-041: with ``background`` there is no limit of one request; the report is part of the task."""
        text = "Name;Ort\nKulturverein;Dorf\nSportverein;Stadt\n"
        refused = self.admin.post(f"{API}/imports/customers", {"file": csv_file("k.csv", text)}, format="multipart")
        self.assert_error(refused, 400, "validation_error")
        started = self.admin.post(
            f"{API}/imports/customers",
            {"file": csv_file("k.csv", text), "dry_run": "false", "background": "true"},
            format="multipart",
        )
        self.assertEqual(started.status_code, 202, started.content)
        job = self.admin.get(f"{API}/jobs/{started.json()['id']}").json()
        self.assertEqual((job["status"], job["result"]["report"]["created"]), ("done", 2))
        self.assertEqual(Customer.objects.count(), 2)


class FullExportApiTests(ApiTestCase):
    def test_export_for_administrators(self) -> None:
        started = self.admin.post(f"{API}/exports/full")
        self.assertEqual(started.status_code, 202, started.content)
        job = started.json()
        self.assertEqual(job["status"], "done")
        result = self.admin.get(job["result_url"])
        with zipfile.ZipFile(io.BytesIO(b"".join(result.streaming_content))) as archive:
            self.assertIn("LIESMICH.txt", archive.namelist())
        self.assert_error(self.client_for("nora", "Nur-Lesen").post(f"{API}/exports/full"), 403, "permission_denied")
