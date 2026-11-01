# SPDX-License-Identifier: GPL-3.0-or-later
"""The customer's name shows in every role at projects and service cases (PRJ-122).

The requirement: the customer's name is shown in every role at projects and service cases; where it is not visible
to a role today (because the right to customers is missing), the name shown is not clickable.

The name of the customer shows in every role (AUT-023): for
the projects and cases the role sees; it is a link only for who may read customers. Everything else of the customer's
side – contact, who reported a case, the customer's page, a list of its projects – stays with the right to see them.
"""

from __future__ import annotations

from django.urls import reverse

from rentalars.projects import service_cases
from rentalars.projects.case_list_table import without_contacts
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_project
from tests.ui.base import UiTestCase
from tests.unit.test_091_rights import CustomerSideScene


class CaseNameTests(CustomerSideScene, UiTestCase):
    """The page and the list of a service case, as Kai (Crew, taking part, no customers) and Paula read them."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.kai_browser = self.browser_of(self.kai_user)
        self.paula_browser = self.browser_of(self.paula)
        self.url = reverse("projects:case_detail", args=[self.case])
        self.name = self.case.customer.name

    def test_the_page_names_the_customer_without_a_link(self) -> None:
        page = self.assert_ok(self.kai_browser.get(self.url))
        self.assertIn(self.name, page)
        self.assertNotIn("/customers/", page)
        # The contact and who reported the case stay with the right to see customers.
        for hidden in ("Hausmeister", "0170 1234567", "Gemeldet von"):
            self.assertNotIn(hidden, page)

    def test_who_may_read_customers_gets_the_link_and_the_contact(self) -> None:
        page = self.assert_ok(self.paula_browser.get(self.url))
        self.assertIn(f'<a href="{reverse("customers:detail", args=[self.case.customer_id])}">{self.name}</a>', page)
        self.assertIn("Hausmeister", page)

    def test_the_list_names_the_customer_but_not_the_contact(self) -> None:
        page = self.assert_ok(self.kai_browser.get(reverse("projects:cases")))
        self.assertIn(self.name, page)
        for hidden in ("Max Muster", "Hausmeister"):
            self.assertNotIn(hidden, page)
        csv = self.kai_browser.get(reverse("projects:cases"), {"format": "csv"}).content.decode("utf-8-sig")
        self.assertIn(self.name, csv)
        for hidden in ("Max Muster", "Hausmeister"):
            self.assertNotIn(hidden, csv)
        listed = self.assert_ok(self.paula_browser.get(reverse("projects:cases")))
        self.assertIn("Max Muster", listed)

    def test_the_search_finds_by_the_name_but_not_by_the_reporter(self) -> None:
        found = self.assert_ok(self.kai_browser.get(reverse("projects:cases"), {"q": self.name}))
        self.assertIn("Spot flackert", found)
        found = self.assert_ok(self.kai_browser.get(reverse("projects:cases"), {"q": "Hausmeister"}))
        self.assertNotIn("Spot flackert", found)
        found = self.assert_ok(self.paula_browser.get(reverse("projects:cases"), {"q": "Hausmeister"}))
        self.assertIn("Spot flackert", found)

    def test_without_contacts_leaves_the_name(self) -> None:
        (case,) = [
            each
            for each in service_cases.case_list(service_cases.cases(type(self.case).objects.all()))
            if each.pk == self.case.pk
        ]
        shown = next(iter(without_contacts([case])))
        self.assertEqual((shown.contact_id, shown.case_contact, shown.customer.name), (None, "", self.name))


class CaseNameApiTests(CustomerSideScene, ApiTestCase):
    """The API of a case and of a project names the customer in every role; the customer record stays hidden."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.kai_api = self.client_of(self.kai_user)

    def test_a_case(self) -> None:
        data = self.kai_api.get(f"{API}/service-cases/{self.case.pk}").json()
        self.assertEqual(data["customer_name"], self.case.customer.name)
        self.assertEqual((data["customer"], data["contact"], data["case_contact"]), (None, None, ""))
        listed = self.kai_api.get(f"{API}/service-cases").json()["results"]
        self.assertEqual({row["customer_name"] for row in listed}, {self.case.customer.name})
        self.assertEqual(
            self.client_of(self.paula).get(f"{API}/service-cases/{self.case.pk}").json()["customer"],
            self.case.customer_id,
        )

    def test_a_case_without_customer_and_an_internal_project(self) -> None:
        internal = service_cases.create_case(name="Eigene Kiste", is_internal=True, manager=self.paula, user=self.paula)
        self.assertIsNone(self.client_of(self.paula).get(f"{API}/service-cases/{internal.pk}").json()["customer_name"])
        project = make_project("Hallenumbau", customer=make_customer("Halle GmbH"))
        data = self.client_of(self.paula).get(f"{API}/projects/{project.pk}").json()
        self.assertEqual(data["customer_name"], "Halle GmbH")
