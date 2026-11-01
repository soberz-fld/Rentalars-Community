# SPDX-License-Identifier: GPL-3.0-or-later
"""API: the customer import with a Lexware export reports the outcome of every row (IMP-013)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.customers.models import Customer
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer
from tests.unit.test_customer_import_merge import KULTURVEREIN, PRIVATE, lexware_file


class CustomerImportMergeApiTests(ApiTestCase):
    def test_rows_in_the_report(self) -> None:
        known = make_customer("KV Dorf")
        known.vat_id = "DE123456789"
        known.save()
        upload = SimpleUploadedFile("kontakte.csv", lexware_file(KULTURVEREIN, PRIVATE), content_type="text/csv")
        response = self.admin.post(f"{API}/imports/customers", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["mapping"]["street"], "Straße 1")
        self.assertEqual(
            [(row["row"], row["outcome"], row["found_by"], row["customer"]) for row in body["rows"]],
            [(2, "merged", "vat_id", known.number), (3, "created", "", "20002")],
        )
        self.assertIn("gefunden über die USt-IdNr.", body["rows"][0]["text"])
        self.assertEqual(Customer.objects.count(), 1)  # a dry run by default
