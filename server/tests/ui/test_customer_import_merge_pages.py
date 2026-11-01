# SPDX-License-Identifier: GPL-3.0-or-later
"""The customer import page with a Lexware export and its report per row (IMP-013)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.customers.models import Customer
from tests.helpers import make_customer
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_customer_import_merge import KULTURVEREIN, PRIVATE, lexware_file


class LexwareImportPageTests(UiTestCase):
    def test_dry_run_names_the_outcome_of_every_row(self) -> None:
        known = make_customer("KV Dorf")
        known.vat_id = "DE123456789"
        known.save()
        url = reverse("core:import", args=["customers"])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Kontaktexport aus Lexware", page)
        upload = SimpleUploadedFile("kontakte.csv", lexware_file(KULTURVEREIN, PRIVATE), content_type="text/csv")
        self.client.post(url, {"step": "upload", "file": upload})
        mapping = self.client.get(url)
        text = self.assert_ok(mapping)
        self.assertIn("Straße 1", text)  # read as Windows-1252, not as "Stra�e 1"
        data = form_data(mapping, containing="map_name")
        self.assertEqual((data["map_name"], data["map_street"], data["map_delivery_street"]), ("2", "10", "15"))

        checked = self.assert_ok(self.client.post(url, {**data, "step": "check"}, follow=True))
        self.assertIn("1 neu, 1 geändert, 0 unverändert", checked)
        self.assertIn(f"zusammengeführt mit {known.number} „KV Dorf“ (gefunden über die USt-IdNr.)", checked)
        self.assertIn("Die Spalte „Lieferantennummer“ wird nicht übernommen.", checked)
        self.assertIn("Ansprechperson Eva Müller hinzugefügt", checked)
        self.assertEqual(Customer.objects.count(), 1)

        done = self.assert_ok(self.client.post(url, {**data, "step": "import"}, follow=True))
        self.assertIn("Der Import ist abgeschlossen.", done)
        self.assertEqual(Customer.objects.count(), 2)
        detail = self.assert_ok(self.client.get(reverse("customers:detail", args=[known.pk])))
        self.assertIn("12/345/67890", detail)
        self.assertIn("Frau Eva Müller", detail)

    def test_the_exported_list_with_tax_number_comes_back_unchanged(self) -> None:
        customer = make_customer("Kulturverein")
        customer.tax_number, customer.email, customer.phone = "12/345/67890", "k@v.example", "0123 4"
        customer.save()
        exported = self.client.get(reverse("customers:list"), {"format": "csv", "cols": "all"}).content
        self.assertIn("Steuernummer", exported.decode("utf-8"))
        url = reverse("core:import", args=["customers"])
        self.client.post(url, {"step": "upload", "file": SimpleUploadedFile("kunden.csv", exported)})
        data = form_data(self.client.get(url), containing="map_name")
        text = self.assert_ok(self.client.post(url, {**data, "step": "check"}, follow=True))
        self.assertIn("0 neu, 0 geändert, 1 unverändert", text)
        self.assertFalse(customer.contacts.exists())

    def test_contact_form_has_the_salutation(self) -> None:
        customer = make_customer("Kulturverein")
        page = self.client.get(reverse("customers:contact_create", args=[customer.pk]))
        data = form_data(
            page, containing="salutation", salutation="Frau", first_name="Eva", last_name="Müller"
        )  # Split name
        self.client.post(reverse("customers:contact_create", args=[customer.pk]), data)
        self.assertEqual(customer.contacts.get().salutation, "Frau")
