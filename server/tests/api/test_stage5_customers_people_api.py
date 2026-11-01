# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of stage 5 for customers, people, products and timelines (KND-005 to KND-008, PER-014, PRD-020)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.personnel.models import QualificationType
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, at, job_function, make_customer, make_person, make_project, make_stock, plan


class CustomerApiTests(ApiTestCase):
    """KND-005, KND-006, KND-008."""

    def test_commercial_details_and_duplicates(self) -> None:
        make_customer("Stadtwerke Musterstadt GmbH")
        response = self.admin.post(
            f"{API}/customers",
            {"name": "Stadtwerke Musterstadt", "vat_id": "de123456789", "payment_terms_days": 30,
             "default_discount_percent": "5.00"},
            format="json",
        )  # fmt: skip
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["vat_id"], body["payment_terms_days"]), ("DE123456789", 30))
        self.assertEqual([entry["name"] for entry in body["possible_duplicates"]], ["Stadtwerke Musterstadt GmbH"])
        found = self.admin.get(f"{API}/customers/duplicates", {"name": "stadtwerke musterstadt"}).json()
        self.assertEqual(len(found), 2)
        warehouse = self.client_for("luka", "Lager")
        self.assertNotIn("default_discount_percent", warehouse.get(f"{API}/customers/{body['id']}").json())
        self.assert_error(
            self.admin.patch(f"{API}/customers/{body['id']}", {"vat_id": "12345"}, format="json"),
            400,
            "validation_error",
            "vat_id",
        )

    def test_addresses(self) -> None:
        customer = make_customer()
        url = f"{API}/customers/{customer.pk}/addresses"
        created = self.admin.post(url, {"kind": "billing", "street": "Rathaus", "city": "M"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        address = created.json()["id"]
        self.assertEqual(len(self.admin.get(url).json()), 1)
        self.assertEqual(self.admin.get(f"{url}/{address}").json()["city"], "M")
        self.admin.patch(f"{url}/{address}", {"is_default": True}, format="json")
        replaced = self.admin.put(
            f"{url}/{address}", {"kind": "billing", "street": "Markt 1", "city": "M", "is_default": True}, format="json"
        )
        self.assertEqual(replaced.status_code, 200)
        project = make_project(customer=customer)
        # KND-005: a new project takes the default address of its customer.
        self.assertEqual(self.admin.get(f"{API}/projects/{project.pk}").json()["billing_address"], address)
        changed = self.admin.patch(f"{API}/projects/{project.pk}", {"billing_address": None}, format="json")
        self.assertIsNone(changed.json()["billing_address"])
        changed = self.admin.patch(f"{API}/projects/{project.pk}", {"billing_address": address}, format="json")
        self.assertEqual(changed.json()["billing_address"], address)
        foreign = make_customer("Andere")
        # An address of another customer is refused …
        self.assert_error(
            self.admin.patch(
                f"{API}/projects/{project.pk}", {"customer": foreign.pk, "billing_address": address}, format="json"
            ),
            400,
            "validation_error",
        )
        # … and a new customer brings its own defaults.
        moved = self.admin.patch(f"{API}/projects/{project.pk}", {"customer": foreign.pk}, format="json")
        self.assertEqual((moved.status_code, moved.json()["billing_address"]), (200, None))
        self.admin.patch(f"{API}/projects/{project.pk}", {"customer": customer.pk}, format="json")
        self.assertEqual(self.admin.delete(f"{url}/{address}").status_code, 204)


class QualificationApiTests(ApiTestCase):
    """PER-014."""

    def test_types_and_qualifications(self) -> None:
        created = self.admin.post(
            f"{API}/qualification-types", {"name": "Ersthelfer", "validity_months": 24}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)
        kind = created.json()["id"]
        self.assertEqual(len(self.admin.get(f"{API}/qualification-types").json()), 1)
        self.assertEqual(self.admin.get(f"{API}/qualification-types/{kind}").json()["validity_months"], 24)
        self.admin.patch(f"{API}/qualification-types/{kind}", {"validity_months": 36}, format="json")
        self.admin.put(
            f"{API}/qualification-types/{kind}", {"name": "Ersthelfer", "validity_months": 24}, format="json"
        )

        person = make_person("Anna Beispiel")
        url = f"{API}/people/{person.pk}/qualifications"
        response = self.admin.post(
            url,
            {
                "qualification_type": kind,
                "acquired_on": "2025-04-01",
                "document": SimpleUploadedFile("kurs.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["valid_until"], body["state"]), ("2027-04-01", "soon"))
        self.assertEqual(len(self.admin.get(url).json()), 1)
        detail = f"{url}/{body['id']}"
        self.assertEqual(self.admin.get(detail).json()["document_name"], "kurs.pdf")
        renewed = self.admin.patch(detail, {"valid_until": "2029-04-01"}, format="json").json()
        self.assertEqual(renewed["state"], "valid")
        certificate = self.admin.get(f"{detail}/certificate")
        self.assertEqual(certificate.status_code, 200)
        self.assert_error(self.admin.delete(f"{API}/qualification-types/{kind}"), 400, "validation_error")
        self.assertEqual(self.admin.delete(detail).status_code, 204)
        self.assertEqual(self.admin.delete(f"{API}/qualification-types/{kind}").status_code, 204)
        crew = self.client_for("tom", "Crew")
        self.assertEqual(crew.get(url).status_code, 403)

    def test_person_timeline(self) -> None:
        person = make_person("Anna Beispiel", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest", start=at(2, 8), end=at(3, 18)), job_function("Tontechnik"), person)
        QualificationType.objects.create(name="Unbenutzt")
        timeline = self.admin.get(f"{API}/people/{person.pk}/timeline", {"from": "2027-03-01", "weeks": 1}).json()
        self.assertEqual(len(timeline["days"]), 7)
        self.assertEqual(timeline["rows"][0]["bars"][0]["from"], "2027-03-02")


class ProductApiTests(ApiTestCase):
    """PRD-020, VFG-019."""

    def test_minimum_stock_and_timeline(self) -> None:
        product = make_stock("K-005", 3, "XLR-Kabel")
        other = make_stock("K-010", 9)
        self.admin.patch(f"{API}/products/{product.pk}", {"minimum_stock": 5}, format="json")
        listed = self.admin.get(f"{API}/products", {"below_minimum": "true"}).json()["results"]
        self.assertEqual([row["id"] for row in listed], [product.pk])
        self.assertTrue(other.pk)
        add_line(make_project("Stadtfest"), product, 2)
        timeline = self.admin.get(f"{API}/products/{product.pk}/timeline", {"from": "2027-03-08", "weeks": 1}).json()
        free = timeline["rows"][0]["free"]
        self.assertEqual([day["free"] for day in free[:5]], [3, 3, 1, 1, 3])
