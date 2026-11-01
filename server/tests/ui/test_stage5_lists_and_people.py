# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of stage 5: every list with columns and CSV, calendar week, timelines, customers, qualifications.

UIX-015, IMP-005, PRJ-067, VFG-019, PER-020, KND-005, KND-006, KND-008, PER-014, PRD-020.
"""

from __future__ import annotations

import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.customers.models import Customer, CustomerAddress, Venue
from rentalars.personnel.models import Qualification, QualificationType
from rentalars.projects.models import Project
from tests.helpers import add_line, at, job_function, make_customer, make_person, make_project, make_stock, plan
from tests.ui.base import UiTestCase, form_data


class EveryListTests(UiTestCase):
    """UIX-015: each list has the column chooser, sortable headings and CSV of the filtered view."""

    LISTS = {
        "projects:list": ("projects", "Nummer"),
        "products:list": ("products", "Art.-Nr."),
        "material:model_list": ("material_models", "Artikelname"),
        "material:item_list": ("material_items", "ID"),
        "customers:list": ("customers", "Name"),
        "customers:venue_list": ("venues", "Name"),
        "personnel:person_list": ("people", "Name"),
        "personnel:job_function_list": ("job_functions", "Funktion"),
        "accounts:user_list": ("users", "Nutzer"),
    }

    def setUp(self) -> None:
        super().setUp()
        make_project("Stadtfest")
        make_stock("K-005", 2)
        make_person("Anna Beispiel", rates={"Tontechnik": "35.00"})
        Venue.objects.create(name="Stadthalle", city="Musterstadt")

    def test_chooser_headings_and_csv(self) -> None:
        for name, (key, first_heading) in self.LISTS.items():
            with self.subTest(list=name):
                url = reverse(name)
                page = self.assert_ok(self.client.get(url))
                self.assertIn(reverse("core:table_columns", args=[key]), page)
                self.assertIn('scope="col"', page)
                response = self.client.get(url, {"format": "csv"})
                self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
                header = response.content.decode("utf-8-sig").splitlines()[0]
                self.assertTrue(header.startswith(first_heading), header)
                every = self.client.get(url, {"format": "csv", "cols": "all"}).content.decode("utf-8-sig")
                self.assertGreater(len(every.splitlines()[0]), len(header))

    def test_more_columns_and_sorting_of_projects(self) -> None:
        make_project("Abiball", start=at(20), end=at(21))
        page = self.assert_ok(
            self.client.get(reverse("projects:list"), {"cols": "name,status,venue,created", "sort": "-name"})
        )
        self.assertIn("Veranstaltungsort", page)
        self.assertNotIn("Projektleitung</a>", page)
        self.assertLess(page.index("Stadtfest"), page.index("Abiball"))

    def test_crew_sees_no_customer_column(self) -> None:
        crew = self.browser_for("tom", "Crew")
        self.client.post(reverse("core:table_columns", args=["projects"]), {"columns": ["customer"], "next": "/"})
        page = crew.get(reverse("projects:list"), {"cols": "all"}).content.decode()
        self.assertNotIn("Kundennummer", page)


class CalendarWeekTests(UiTestCase):
    """PRJ-067: month or week, the choice is remembered."""

    def test_week_with_times_and_memory(self) -> None:
        project = make_project("Stadtfest", start=at(2, 8), end=at(4, 18))
        page = self.assert_ok(self.client.get(reverse("schedule:calendar"), {"view": "week", "week": "2027-03-03"}))
        self.assertIn("KW 9", page)
        self.assertIn("ab 08:00", page)
        self.assertIn("ganztägig", page)
        self.assertIn("bis 18:00", page)
        self.assertIn(reverse("projects:detail", args=[project.pk]), page)
        again = self.assert_ok(self.client.get(reverse("schedule:calendar")))
        self.assertIn("KW 9", again)
        month = self.assert_ok(self.client.get(reverse("schedule:calendar"), {"view": "month"}))
        self.assertIn("März 2027", month)
        self.assertIn("März 2027", self.assert_ok(self.client.get(reverse("schedule:calendar"))))


class TimelinePageTests(UiTestCase):
    """VFG-019 product, PER-020 person."""

    def test_product_timeline_and_low_stock(self) -> None:
        product = make_stock("K-005", 3, "XLR-Kabel")
        add_line(make_project("Stadtfest"), product, 2)
        page = self.assert_ok(self.client.get(reverse("products:timeline", args=[product.pk]), {"weeks": "2"}))
        self.assertIn("Stadtfest", page)
        self.assertIn("Zeitstrahl", page)
        edit = reverse("products:edit", args=[product.pk])
        self.client.post(edit, form_data(self.client.get(edit), minimum_stock="5"))
        product.refresh_from_db()
        self.assertEqual(product.minimum_stock, 5)
        self.assertIn(
            "unter dem Mindestbestand", self.assert_ok(self.client.get(reverse("products:detail", args=[product.pk])))
        )
        listed = self.assert_ok(self.client.get(reverse("products:list"), {"below_minimum": "1"}))
        self.assertIn("K-005", listed)

    def test_person_timeline(self) -> None:
        person = make_person("Anna Beispiel", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest", start=at(2, 8), end=at(3, 18)), job_function("Tontechnik"), person)
        page = self.assert_ok(self.client.get(reverse("personnel:person_timeline", args=[person.pk])))
        self.assertIn("Stadtfest · Tontechnik", page)
        self.assertIn("abwesend", page)


class CustomerStage5Tests(UiTestCase):
    """KND-005, KND-006, KND-008."""

    def test_duplicate_warning_needs_a_second_yes(self) -> None:
        make_customer("Stadtwerke Musterstadt GmbH")
        url = reverse("customers:create")
        data = form_data(self.client.get(url), name="Stadtwerke Musterstadt", vat_id="de 123456789")
        response = self.client.post(url, data)
        self.assertIn("Diesen Kunden gibt es vielleicht schon", self.assert_ok(response))
        self.assertEqual(Customer.objects.count(), 1)
        live = self.client.get(reverse("customers:duplicates"), {"name": "stadtwerke musterstadt"})
        self.assertIn("ähnlicher Name", live.content.decode())
        self.client.post(url, {**data, "confirm_duplicate": "on"})
        self.assertEqual(Customer.objects.get(name="Stadtwerke Musterstadt").vat_id, "DE123456789")

    def test_addresses_and_project(self) -> None:
        customer = make_customer("Messe GmbH")
        url = reverse("customers:address_create", args=[customer.pk])
        self.client.post(url, {"kind": "delivery", "street": "Halle 7", "city": "Messestadt", "is_default": "on"})
        address = CustomerAddress.objects.get()
        detail = self.assert_ok(self.client.get(reverse("customers:detail", args=[customer.pk])))
        self.assertIn("Halle 7", detail)
        create = self.client.get(reverse("projects:create"), {"customer": customer.pk})
        data = form_data(create, name="Messeauftritt")
        self.assertEqual(data["delivery_address"], str(address.pk))
        self.client.post(reverse("projects:create"), data)
        self.assertEqual(Project.objects.get(name="Messeauftritt").delivery_address, address)
        self.client.post(reverse("customers:address_delete", args=[customer.pk, address.pk]))
        self.assertIsNone(Project.objects.get(name="Messeauftritt").delivery_address)

    def test_default_addresses_when_the_customer_is_chosen_in_the_form(self) -> None:
        """KND-005: Projekte → Neues Projekt knows the customer only on saving; its defaults still apply."""
        customer = make_customer("Messe GmbH")
        billing = CustomerAddress.objects.create(
            customer=customer, kind="billing", street="Buchhaltung 1", city="Messestadt", is_default=True
        )
        other = make_customer("Stadt")
        delivery = CustomerAddress.objects.create(
            customer=other, kind="delivery", street="Bauhof", city="Stadt", is_default=True
        )
        data = form_data(self.client.get(reverse("projects:create")), name="Messeauftritt", customer=str(customer.pk))
        self.assertEqual(data["addresses_for"], "")
        self.client.post(reverse("projects:create"), data)
        project = Project.objects.get(name="Messeauftritt")
        self.assertEqual((project.billing_address, project.delivery_address), (billing, None))

        edit = reverse("projects:edit", args=[project.pk])
        data = form_data(self.client.get(edit), containing="addresses_for", customer=str(other.pk))
        self.assertEqual((data["addresses_for"], data["billing_address"]), (str(customer.pk), str(billing.pk)))
        response = self.client.post(edit, data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:300])
        project.refresh_from_db()
        self.assertEqual((project.customer, project.billing_address, project.delivery_address), (other, None, delivery))

    def test_discount_only_with_price_right(self) -> None:
        customer = make_customer()
        warehouse = self.browser_for("luka", "Lager")
        self.assertNotIn(
            "default_discount_percent", warehouse.get(reverse("customers:edit", args=[customer.pk])).content.decode()
        )
        self.assertIn(
            "default_discount_percent", self.client.get(reverse("customers:edit", args=[customer.pk])).content.decode()
        )


class QualificationPageTests(UiTestCase):
    """PER-014: record, renew, show to the person, remove."""

    def test_record_show_and_remove(self) -> None:
        person = make_person("Anna Beispiel")
        kind = QualificationType.objects.create(name="Ersthelfer", validity_months=24)
        url = reverse("personnel:qualification_create", args=[person.pk])
        self.assert_ok(self.client.get(url))
        self.client.post(
            url,
            {
                "qualification_type": kind.pk,
                "acquired_on": "2025-04-01",
                "upload": SimpleUploadedFile("kurs.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"),
            },
        )
        qualification = Qualification.objects.get()
        self.assertEqual(qualification.valid_until, datetime.date(2027, 4, 1))
        page = self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[person.pk])))
        self.assertIn("Ersthelfer bis 01.04.2027", page)
        document = reverse("personnel:qualification_document", args=[person.pk, qualification.pk])
        self.assertEqual(self.client.get(document).status_code, 200)
        # Somebody else with a login of the role Crew may not see it; the person herself may (AUT-026).
        stranger = self.browser_for("tom", "Crew")
        self.assertEqual(stranger.get(document).status_code, 403)
        herself = self.browser_of(person.user)
        self.assertEqual(herself.get(document).status_code, 200)
        self.assertIn("Meine Qualifikationen", herself.get(reverse("personnel:own_profile")).content.decode())
        self.client.post(reverse("personnel:qualification_delete", args=[person.pk, qualification.pk]))
        self.assertFalse(Qualification.objects.exists())
