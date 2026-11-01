# SPDX-License-Identifier: GPL-3.0-or-later
"""A new contact person from the project form (PRJ-140) and the tab "Fuhrpark" after "Exemplare" (UIX-013).

The requirement: when a project is created, the contacts of the customer can be chosen, but a new contact could not be
created there. The dropdown therefore also shows "new contact", which opens a pop-up to create one.

* The contact field lists the contacts of the customer and, last, "Neuer Ansprechpartner …" (a choice with the address of
  the dialog) – for whoever may change the customers, and when a customer is chosen.
* The dialog asks for the name and the ways to reach the person; saving closes it and names the new contact for the field.
* The new contact belongs to the customer; the first one becomes the primary contact.
* The choice is no value: sent all the same, the form says so and nothing is saved; the same person sent twice
  is added once; an anonymised customer gets neither the choice nor a new contact.
"""

from __future__ import annotations

import json

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module
from rentalars.customers.models import Contact
from rentalars.projects.models import Project
from tests.helpers import make_customer
from tests.ui.base import UiTestCase, form_data

NEW = "__new__"


class ContactDialogTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadtwerke Musterstadt")
        self.anna = Contact.objects.create(
            customer=self.customer, name="Anna Berg", last_name="Berg", first_name="Anna"
        )
        self.dialog = reverse("customers:contact_quick_create", args=[self.customer.pk])

    def form_page(self, client=None) -> str:
        return self.assert_ok((client or self.client).get(reverse("projects:create"), {"customer": self.customer.pk}))

    def test_the_last_choice_of_the_contact_field_opens_the_dialog(self) -> None:
        page = self.form_page()
        self.assertIn("Neuer Ansprechpartner", page)
        self.assertIn(f'data-create-url="{self.dialog}?field=contact"', page)
        select = page[page.index('name="contact"') :]
        select = select[: select.index("</select>")]
        self.assertLess(select.index("Anna Berg"), select.index("Neuer Ansprechpartner"))
        self.assertIn(f'value="{NEW}"', select)

    def test_without_a_customer_there_is_nothing_to_create_for(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:create")))
        self.assertNotIn("Neuer Ansprechpartner", page)

    def test_whoever_may_not_change_customers_is_not_offered_the_choice(self) -> None:
        Role.objects.create(
            name="Projektleiter",
            module_levels={Module.PROJECTS: int(Level.WRITE), Module.CUSTOMERS: int(Level.READ)},
        )
        browser = self.browser_for("pia", "Projektleiter")
        page = self.form_page(browser)
        self.assertIn("Anna Berg", page)
        self.assertNotIn("Neuer Ansprechpartner", page)
        self.assertEqual(browser.get(self.dialog).status_code, 403)

    def test_the_dialog_asks_for_the_name_and_ways_to_reach_the_person(self) -> None:
        response = self.client.get(self.dialog, {"field": "contact"})
        page = self.assert_ok(response)
        for name in ("salutation", "first_name", "last_name", "position", "email", "phone"):
            self.assertIn(f'name="{name}"', page)
        for name in ("is_primary", "greeting_style", "greeting_text"):
            self.assertNotIn(f'name="{name}"', page)
        self.assertIn("Stadtwerke Musterstadt", page)

    def test_saving_creates_the_contact_and_tells_the_field(self) -> None:
        response = self.client.post(
            f"{self.dialog}?field=contact",
            {"salutation": "Frau", "first_name": "Berta", "last_name": "Klein", "email": "berta@example.de"},
        )
        self.assertEqual(response.status_code, 204)
        contact = Contact.objects.get(last_name="Klein")
        self.assertEqual(
            (contact.customer, contact.name, contact.email), (self.customer, "Berta Klein", "berta@example.de")
        )
        trigger = json.loads(response["HX-Trigger"])
        self.assertTrue(trigger["closeDialog"])
        self.assertEqual(trigger["objectCreated"], {"field": "contact", "id": contact.pk, "label": "Berta Klein"})
        self.assertFalse(contact.is_primary)  # Anna is the primary one

    def test_the_first_contact_of_a_customer_becomes_the_primary_one(self) -> None:
        other = make_customer("Messe GmbH")
        self.client.post(
            reverse("customers:contact_quick_create", args=[other.pk]), {"first_name": "Carl", "last_name": "Dorn"}
        )
        self.assertTrue(Contact.objects.get(customer=other).is_primary)

    def test_a_last_name_is_needed(self) -> None:
        response = self.client.post(self.dialog, {"first_name": "Berta"})
        page = self.assert_ok(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nachname", page)
        self.assertEqual(Contact.objects.count(), 1)

    def test_only_with_the_right_and_only_by_post(self) -> None:
        browser = self.browser_for("rita", "Nur-Lesen")
        self.assertEqual(browser.get(self.dialog).status_code, 403)
        self.assertEqual(browser.post(self.dialog, {"last_name": "X"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("customers:contact_quick_create", args=[9999])).status_code, 404)
        self.assertEqual(Contact.objects.count(), 1)

    def test_the_new_contact_can_be_chosen_when_the_project_is_saved(self) -> None:
        self.client.post(self.dialog, {"first_name": "Berta", "last_name": "Klein"})
        berta = Contact.objects.get(last_name="Klein")
        page = self.client.get(reverse("projects:create"), {"customer": self.customer.pk})
        data = form_data(page, containing="name", name="Stadtfest", contact=str(berta.pk))
        self.client.post(reverse("projects:create"), data)
        self.assertEqual(Project.objects.get(name="Stadtfest").contact, berta)

    def test_the_choice_itself_is_no_contact(self) -> None:
        page = self.client.get(reverse("projects:create"), {"customer": self.customer.pk})
        data = form_data(page, containing="name", name="Stadtfest", contact=NEW)
        response = self.client.post(reverse("projects:create"), data)
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)  # the form is shown again, with the reason
        self.assertTrue(
            "dialog for a new contact person did not open" in content
            or "Dialog für den neuen Ansprechpartner" in content
        )
        self.assertNotIn("Select a valid choice", content)
        self.assertFalse(Project.objects.filter(name="Stadtfest").exists())

    def test_the_same_person_sent_twice_is_added_once(self) -> None:
        person = {"first_name": "Berta", "last_name": "Klein", "email": "berta@example.de"}
        first = self.client.post(self.dialog, person)
        second = self.client.post(self.dialog, {**person, "email": "BERTA@example.de"})
        self.assertEqual(Contact.objects.filter(last_name="Klein").count(), 1)
        self.assertEqual(
            json.loads(first["HX-Trigger"])["objectCreated"]["id"],
            json.loads(second["HX-Trigger"])["objectCreated"]["id"],
        )

    def test_an_anonymised_customer_gets_no_new_contacts(self) -> None:
        from django.utils import timezone

        other = make_customer("Alt GmbH")
        other.anonymised_at = timezone.now()
        other.save(update_fields=["anonymised_at"])
        dialog = reverse("customers:contact_quick_create", args=[other.pk])
        response = self.client.post(dialog, {"first_name": "Carl", "last_name": "Dorn"})
        self.assertEqual(response.status_code, 200)  # the dialog stays open with the reason
        self.assertFalse(Contact.objects.filter(customer=other).exists())
        page = self.assert_ok(self.client.get(reverse("projects:create"), {"customer": other.pk}))
        self.assertNotIn("Neuer Ansprechpartner", page)

    def test_the_part_of_a_project_and_the_edit_form_offer_it_too(self) -> None:
        from tests.helpers import make_project

        project = make_project("Messe", customer=self.customer)
        page = self.assert_ok(self.client.get(reverse("projects:edit", args=[project.pk])))
        self.assertIn("Neuer Ansprechpartner", page)
        part = self.assert_ok(self.client.get(reverse("projects:subproject_create", args=[project.pk])))
        self.assertIn("Neuer Ansprechpartner", part)


class CaseContactDialogTests(UiTestCase):
    """The form of a service case offers the same last choice for the contact (PRJ-140)."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadtwerke Musterstadt")
        self.anna = Contact.objects.create(
            customer=self.customer, name="Anna Berg", last_name="Berg", first_name="Anna"
        )
        self.dialog = reverse("customers:contact_quick_create", args=[self.customer.pk])

    def test_a_new_case_offers_the_choice_once_the_customer_is_chosen(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:case_create"), {"customer": self.customer.pk}))
        self.assertIn("Neuer Ansprechpartner", page)
        self.assertIn(f'data-create-url="{self.dialog}?field=contact"', page)
        select = page[page.index('name="contact"') :]
        select = select[: select.index("</select>")]
        self.assertLess(select.index("Anna Berg"), select.index("Neuer Ansprechpartner"))

    def test_without_a_customer_there_is_nothing_to_create_for(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:case_create")))
        self.assertNotIn("Neuer Ansprechpartner", page)

    def test_the_edit_form_of_a_case_offers_it_too(self) -> None:
        from tests.helpers import make_project

        case = make_project("Defekt Pult", customer=self.customer)
        case.kind = "service_case"
        case.save(update_fields=["kind"])
        page = self.assert_ok(self.client.get(reverse("projects:case_edit", args=[case.pk])))
        self.assertIn("Neuer Ansprechpartner", page)

    def test_whoever_may_not_change_customers_is_not_offered_the_choice(self) -> None:
        Role.objects.create(
            name="Servicekraft",
            module_levels={Module.PROJECTS: int(Level.WRITE), Module.CUSTOMERS: int(Level.READ)},
        )
        browser = self.browser_for("pia", "Servicekraft")
        page = self.assert_ok(browser.get(reverse("projects:case_create"), {"customer": self.customer.pk}))
        self.assertIn("Anna Berg", page)
        self.assertNotIn("Neuer Ansprechpartner", page)

    def test_the_choice_itself_is_no_contact(self) -> None:
        page = self.client.get(reverse("projects:case_create"), {"customer": self.customer.pk})
        data = form_data(page, containing="name", name="Pult defekt", customer=self.customer.pk, contact=NEW)
        response = self.client.post(reverse("projects:case_create"), data)
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)  # the form is shown again, with the reason
        self.assertTrue(
            "dialog for a new contact person did not open" in content
            or "Dialog für den neuen Ansprechpartner" in content
        )
        self.assertNotIn("Select a valid choice", content)
        self.assertFalse(Project.objects.filter(name="Pult defekt").exists())
