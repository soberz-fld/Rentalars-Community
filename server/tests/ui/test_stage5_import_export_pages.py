# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of the imports of products, customers and people and of the full export (IMP-001, IMP-004 to IMP-006)."""

from __future__ import annotations

import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.core.models import BackgroundJob
from rentalars.customers.models import Customer
from rentalars.personnel.models import Person
from rentalars.products.models import Product
from tests.helpers import job_function, make_customer, make_person, make_product, make_user
from tests.ui.base import UiTestCase, form_data


def csv_upload(name: str, text: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class GenericImportPageTests(UiTestCase):
    def test_customers_in_three_steps(self) -> None:
        url = reverse("core:import", args=["customers"])
        list_page = self.assert_ok(self.client.get(reverse("customers:list")))
        self.assertIn(url, list_page)
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Kunden importieren", page)
        self.assertIn("Welche Spalten werden erkannt?", page)
        self.client.post(
            url, {"step": "upload", "file": csv_upload("kunden.csv", "Firma;PLZ;Ort\nKulturverein;12345;Dorf\n")}
        )
        mapping = self.client.get(url)
        data = form_data(mapping, containing="map_name")
        self.assertEqual((data["map_name"], data["map_postal_code"], data["map_city"]), ("0", "1", "2"))

        checked = self.client.post(url, {**data, "step": "check"}, follow=True)
        text = self.assert_ok(checked)
        self.assertIn("Ergebnis des Probelaufs", text)
        self.assertIn("1 neu, 0 geändert, 0 unverändert", text)
        self.assertFalse(Customer.objects.exists())

        done = self.client.post(url, {**data, "step": "import"}, follow=True)
        self.assertIn("Der Import ist abgeschlossen.", self.assert_ok(done))
        self.assertEqual(Customer.objects.get().city, "Dorf")
        self.assertEqual(BackgroundJob.objects.filter(kind="import").count(), 2)
        self.assertIn('name="file"', self.assert_ok(self.client.get(url)))

    def test_errors_and_rights(self) -> None:
        url = reverse("core:import", args=["people"])
        job_function("Licht")
        self.client.post(
            url, {"step": "upload", "file": csv_upload("leute.csv", "Name;Funktionen\nEva Licht;Ballett\n")}
        )
        data = form_data(self.client.get(url), containing="map_name")
        text = self.assert_ok(self.client.post(url, {**data, "step": "check"}, follow=True))
        self.assertIn("Zeile 2, Funktionen: Eine Funktion „Ballett“ gibt es nicht.", text)
        self.assertNotIn("Jetzt importieren", text)
        self.assertFalse(Person.objects.exclude(user=self.admin_user).exists())  # AUT-026: the admin is a person

        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.get(url).status_code, 403)
        self.assertEqual(warehouse.get(reverse("core:import", args=["customers"])).status_code, 403)
        self.assertEqual(self.client.get("/import/nothing/").status_code, 404)

    def test_an_exported_product_list_comes_back_unchanged(self) -> None:
        """IMP-004, IMP-005: export the list with all columns, import it again – nothing changes."""
        make_product("L-010", 'PAR 64 "Rauch & Nebel"', price="12.00")
        make_product("K-005", "XLR-Kabel; 5 m", price="2.50")
        exported = self.client.get(reverse("products:list"), {"format": "csv", "cols": "all"})
        url = reverse("core:import", args=["products"])
        self.assertIn("Materialexemplare", self.assert_ok(self.client.get(url)))
        self.client.post(url, {"step": "upload", "file": csv_upload("produkte.csv", exported.content.decode("utf-8"))})
        data = form_data(self.client.get(url), containing="map_article_number")
        text = self.assert_ok(self.client.post(url, {**data, "step": "check"}, follow=True))
        # With the start product E-001 and the eight services of the job functions of the start data (PER-037).
        self.assertIn("0 neu, 0 geändert, 11 unverändert", text)
        self.assertEqual(Product.objects.get(article_number="K-005").name, "XLR-Kabel; 5 m")
        self.assertIn('"PAR 64 ""Rauch & Nebel"""', exported.content.decode("utf-8"))

    def test_exported_customers_and_people_come_back_unchanged(self) -> None:
        customer = make_customer("Kultur & Verein")
        customer.street, customer.postal_code, customer.city, customer.email = "Markt 1", "12345", "Dorf", "k@v.example"
        customer.payment_terms_days = 30
        customer.save()
        job_function("Licht", guide="25.00")
        person = make_person("Eva Licht", rates={"Licht": "28.00"})
        person.email, person.postal_code, person.city, person.street = "eva@example.de", "54321", "Stadt", "Weg 2"
        person.save()
        for list_url, key, required in (
            (reverse("customers:list"), "customers", "map_name"),
            (reverse("personnel:person_list"), "people", "map_name"),
        ):
            exported = self.client.get(list_url, {"format": "csv", "cols": "all"}).content.decode("utf-8")
            url = reverse("core:import", args=[key])
            self.client.post(url, {"step": "upload", "file": csv_upload(f"{key}.csv", exported)})
            data = form_data(self.client.get(url), containing=required)
            text = self.assert_ok(self.client.post(url, {**data, "step": "check"}, follow=True))
            # AUT-026: the list of people holds the administrator of the test too.
            unchanged = 2 if key == "people" else 1
            self.assertIn(f"0 neu, 0 geändert, {unchanged} unverändert", text, key)
            self.client.post(url, {"step": "discard"})


class FullExportPageTests(UiTestCase):
    def test_administrators_export_everything(self) -> None:
        make_customer("Kulturverein")
        # IMP-006: the button is on the page "Sicherung", no longer under "Import und Export".
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        self.assertIn("Vollständigen Export erstellen", page)
        response = self.client.post(reverse("core:full_export"), follow=True)
        job = BackgroundJob.objects.get(kind="export")
        self.assertRedirects(response, reverse("core:job", args=[job.pk]))
        self.assertEqual(job.status, "done")
        download = self.client.get(reverse("core:job_result", args=[job.pk]))
        content = b"".join(download.streaming_content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertIn("Kulturverein", archive.read("csv/customers.customer.csv").decode("utf-8-sig"))

        manager = self.browser_for("paula", "Projektleitung")
        self.assertEqual(manager.post(reverse("core:full_export")).status_code, 403)
        # Another administrator does not get the file: it holds the data of everybody.
        other = self.browser_of(make_user("chef", superuser=True))
        self.assertEqual(other.get(reverse("core:job_result", args=[job.pk])).status_code, 404)
        self.assertEqual(other.get(reverse("core:job", args=[job.pk])).status_code, 404)
