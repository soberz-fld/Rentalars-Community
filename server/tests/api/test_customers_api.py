# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: customers and their contact persons (KND)."""

from __future__ import annotations

from rentalars.customers.models import Contact, Customer
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_project


class CustomerTests(ApiTestCase):
    """Customers (KND-001 to KND-010)."""

    def test_customer_number_is_assigned_automatically(self) -> None:
        """KND-002. Also KND-003."""
        first = self.admin.post(f"{API}/customers", {"name": "Stadtwerke Musterstadt"}, format="json")
        second = self.admin.post(f"{API}/customers", {"name": "Jazzclub Beispiel e. V."}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertNotEqual(first.data["number"], second.data["number"])
        ignored = self.admin.post(f"{API}/customers", {"name": "Dritter", "number": "999"}, format="json")
        self.assertNotEqual(ignored.data["number"], "999")

    def test_search_and_filter(self) -> None:
        make_customer("Stadtwerke Musterstadt")
        hidden = make_customer("Jazzclub Beispiel e. V.")
        hidden.is_active = False
        hidden.save()
        found = self.admin.get(f"{API}/customers", {"search": "jazz"}).data["results"]
        self.assertEqual([row["name"] for row in found], ["Jazzclub Beispiel e. V."])
        active = self.admin.get(f"{API}/customers", {"is_active": "true"}).data["results"]
        self.assertEqual([row["name"] for row in active], ["Stadtwerke Musterstadt"])

    def test_contacts_belong_to_one_customer_and_one_is_primary(self) -> None:
        """KND-004."""
        customer = make_customer()
        url = f"{API}/customers/{customer.pk}/contacts"
        first = self.admin.post(
            url, {"name": "Petra Beispiel", "position": "Kulturamt", "email": "petra@example.de"}, format="json"
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data["is_primary"])
        second = self.admin.post(url, {"name": "Tom Technik", "is_primary": True}, format="json")
        self.assertTrue(second.data["is_primary"])
        primary = [row["name"] for row in self.admin.get(url).data if row["is_primary"]]
        self.assertEqual(primary, ["Tom Technik"])
        other = make_customer("Anderer Kunde")
        self.assert_error(self.admin.get(f"{API}/customers/{other.pk}/contacts/{first.data['id']}"), 404, "not_found")

    def test_customer_with_projects_cannot_be_deleted(self) -> None:
        """KND-010."""
        customer = make_customer()
        make_project(customer=customer)
        self.assert_error(self.admin.delete(f"{API}/customers/{customer.pk}"), 400, "validation_error")
        unused = make_customer("Ohne Projekte")
        self.assertEqual(self.admin.delete(f"{API}/customers/{unused.pk}").status_code, 204)

    def test_anonymising_erases_personal_data_but_keeps_the_projects(self) -> None:
        """KND-010: the right to erasure without tearing holes into old projects."""
        customer = make_customer("Miriam Krause")
        customer.street = "Gartenweg 3"
        customer.email = "miriam@example.de"
        customer.save()
        Contact.objects.create(customer=customer, name="Miriam Krause", email="miriam@example.de")
        project = make_project(customer=customer)

        response = self.admin.post(f"{API}/customers/{customer.pk}/anonymise")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.data["anonymised_at"])
        self.assertNotIn("Krause", response.data["name"])
        self.assertEqual(response.data["street"], "")
        self.assertEqual(response.data["email"], "")
        self.assertFalse(Contact.objects.filter(customer=customer).exists())
        self.assertEqual(self.admin.get(f"{API}/projects/{project.pk}").data["customer"], customer.pk)

    def test_anonymising_needs_the_delete_level(self) -> None:
        customer = make_customer()
        manager = self.client_for("paula", "Projektleitung")
        self.assert_error(manager.post(f"{API}/customers/{customer.pk}/anonymise"), 403, "permission_denied")
        self.assertEqual(Customer.objects.get(pk=customer.pk).name, customer.name)

    def test_customers_need_their_module(self) -> None:
        self.assert_error(self.client_for("luka", "Lager").get(f"{API}/customers"), 403, "permission_denied")
