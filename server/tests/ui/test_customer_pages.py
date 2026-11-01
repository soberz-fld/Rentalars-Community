# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: customers and contact persons (KND)."""

from __future__ import annotations

from django.urls import reverse

from rentalars.customers.models import Contact, Customer
from tests.helpers import make_customer, make_project
from tests.ui.base import UiTestCase, form_data


class CustomerPageTests(UiTestCase):
    """Customers in the browser (KND-001 to KND-010)."""

    def test_create_customer_and_contact(self) -> None:
        url = reverse("customers:create")
        response = self.client.post(
            url, form_data(self.client.get(url), name="Stadt Musterstadt, Kulturamt", city="Musterstadt")
        )
        customer = Customer.objects.get(name="Stadt Musterstadt, Kulturamt")
        self.assertRedirects(response, reverse("customers:detail", args=[customer.pk]))
        self.assertTrue(customer.number)

        contact_url = reverse("customers:contact_create", args=[customer.pk])
        self.client.post(
            contact_url,
            # Contact names split: the form has first and last name instead of "name".
            form_data(
                self.client.get(contact_url),
                first_name="Petra",
                last_name="Beispiel",
                position="Kulturamt",
                phone="0123 456",
            ),
        )
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[customer.pk])))
        self.assertIn("Petra Beispiel", page)
        self.assertIn("Hauptkontakt", page)
        self.assertIn(customer.number, page)

    def test_edit_contact_and_delete_it(self) -> None:
        customer = make_customer()
        contact = Contact.objects.create(customer=customer, name="Petra Beispiel")
        url = reverse("customers:contact_edit", args=[customer.pk, contact.pk])
        self.client.post(url, form_data(self.client.get(url), email="petra@example.de"))
        contact.refresh_from_db()
        self.assertEqual(contact.email, "petra@example.de")
        self.client.post(reverse("customers:contact_delete", args=[customer.pk, contact.pk]))
        self.assertFalse(Contact.objects.filter(pk=contact.pk).exists())

    def test_list_search_hides_deactivated_customers_by_default(self) -> None:
        make_customer("Stadtwerke Musterstadt")
        gone = make_customer("Jazzclub Beispiel e. V.")
        gone.is_active = False
        gone.save()
        page = self.assert_ok(self.client.get(reverse("customers:list")))
        self.assertIn("Stadtwerke", page)
        self.assertNotIn("Jazzclub", page)
        self.assertIn("Jazzclub", self.assert_ok(self.client.get(reverse("customers:list"), {"inactive": "1"})))
        self.assertIn(
            "Jazzclub", self.assert_ok(self.client.get(reverse("customers:list"), {"q": "jazz", "inactive": "1"}))
        )

    def test_detail_lists_the_projects_of_the_customer(self) -> None:
        """KND-007."""
        customer = make_customer()
        project = make_project("Stadtfest", customer=customer)
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[customer.pk])))
        self.assertIn(project.number, page)
        self.assertIn("Stadtfest", page)

    def test_delete_is_refused_while_projects_exist_and_anonymise_keeps_them(self) -> None:
        """KND-010."""
        customer = make_customer("Miriam Krause")
        project = make_project(customer=customer)
        refused = self.client.post(reverse("customers:delete", args=[customer.pk]), follow=True)
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())
        self.assertTrue(self.messages_of(refused))

        self.client.post(reverse("customers:anonymise", args=[customer.pk]))
        customer.refresh_from_db()
        self.assertNotIn("Krause", customer.name)
        self.assertIsNotNone(customer.anonymised_at)
        project.refresh_from_db()
        self.assertEqual(project.customer, customer)

    def test_customer_suggestions_for_the_project_form(self) -> None:
        make_customer("Stadtwerke Musterstadt")
        results = self.client.get(reverse("customers:suggest"), {"q": "stadt"}).json()
        # PRJ-070: the last suggestion creates a new customer.
        self.assertEqual(
            [result["label"] for result in results], ["Stadtwerke Musterstadt", "„stadt“ als neuen Kunden anlegen"]
        )

    def test_writing_needs_the_write_level(self) -> None:
        customer = make_customer()
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertEqual(reader.get(reverse("customers:detail", args=[customer.pk])).status_code, 200)
        self.assertEqual(reader.get(reverse("customers:edit", args=[customer.pk])).status_code, 403)
        self.assertEqual(reader.post(reverse("customers:anonymise", args=[customer.pk])).status_code, 403)
