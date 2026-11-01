# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of stage 5 for customers and people (KND-005, KND-006, KND-008, PER-014) and the reports.

Also the daily reports of stage 5: due inspections (MAT-032), expiring
qualifications (PER-014), low stock after an issue (PRD-020).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.accounts.models import User
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress
from rentalars.customers.services import anonymise_customer, find_duplicates, normalised_name
from rentalars.material.inspections import report_due_inspections
from rentalars.material.models import InspectionType
from rentalars.notifications.models import DueNotice, Kind, Notification
from rentalars.personnel.models import Qualification, QualificationType
from rentalars.personnel.privacy import anonymise_person, export_person
from rentalars.personnel.services import check_expiring_qualifications, delete_person, save_qualification
from rentalars.projects.services import update_project
from rentalars.schedule.services import week_calendar
from rentalars.schedule.timelines import person_timeline, product_timeline
from tests.helpers import (
    RentalarsTestCase,
    add_line,
    at,
    category,
    job_function,
    make_customer,
    make_items,
    make_model,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
)


def pdf_file(name: str = "nachweis.pdf") -> SimpleUploadedFile:
    """A small file that passes as PDF."""
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class CustomerAddressTests(RentalarsTestCase):
    """KND-005: further billing and delivery addresses; the project names one of them."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadtwerke Musterstadt")
        self.customer.street, self.customer.postal_code, self.customer.city = "Hauptstraße 1", "12345", "Musterstadt"
        self.customer.save()

    def test_one_default_per_kind_and_the_lines(self) -> None:
        first = CustomerAddress.objects.create(
            customer=self.customer, kind=AddressKind.DELIVERY, street="Lager 1", city="Nordstadt", is_default=True
        )
        second = CustomerAddress.objects.create(
            customer=self.customer, kind=AddressKind.DELIVERY, street="Lager 2", city="Südstadt", is_default=True
        )
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertEqual(self.customer.default_address(AddressKind.DELIVERY), second)
        self.assertEqual(second.address_lines, ["Stadtwerke Musterstadt", "Lager 2", "Südstadt"])

    def test_project_addresses(self) -> None:
        billing = CustomerAddress.objects.create(
            customer=self.customer, kind=AddressKind.BILLING, name="Stadt Musterstadt", street="Rathaus", city="M"
        )
        project = make_project(customer=self.customer)
        self.assertEqual(project.billing_address_lines[0], "Stadtwerke Musterstadt")
        self.assertEqual(project.delivery_address_lines, project.billing_address_lines)
        project.billing_address = billing
        project.venue = "Festplatz"
        project.full_clean()
        self.assertEqual(project.billing_address_lines, ["Stadt Musterstadt", "Rathaus", "M"])
        self.assertEqual(project.delivery_address_lines, ["Festplatz"])
        other = CustomerAddress.objects.create(customer=make_customer("Andere"), street="X", city="Y")
        project.delivery_address = other
        with self.assertRaises(ValidationError):
            project.full_clean()

    def test_new_projects_take_the_default_addresses(self) -> None:
        """KND-005: also a project made through the API or a service, and after a change of customer."""
        billing = CustomerAddress.objects.create(
            customer=self.customer, kind=AddressKind.BILLING, street="Rathaus", city="M", is_default=True
        )
        project = make_project(customer=self.customer)
        self.assertEqual((project.billing_address, project.delivery_address), (billing, None))
        other = make_customer("Andere")
        delivery = CustomerAddress.objects.create(
            customer=other, kind=AddressKind.DELIVERY, street="Lager", city="Y", is_default=True
        )
        with self.assertRaises(ValidationError):
            update_project(project, customer=other, billing_address=billing)
        project.refresh_from_db()
        update_project(project, customer=other)
        project.refresh_from_db()
        self.assertEqual((project.billing_address, project.delivery_address), (None, delivery))
        chosen = make_project(customer=self.customer, billing_address=None)
        self.assertIsNone(chosen.billing_address)

    def test_anonymising_removes_the_addresses(self) -> None:
        CustomerAddress.objects.create(customer=self.customer, street="Lager 1", city="Nordstadt")
        self.customer.vat_id = "DE123456789"
        self.customer.save()
        anonymise_customer(self.customer)
        self.assertFalse(CustomerAddress.objects.exists())
        self.assertEqual(Customer.objects.get().vat_id, "")


class CommercialDetailsTests(RentalarsTestCase):
    """KND-006: VAT ID, payment terms, standard discount."""

    def test_vat_id_is_tidied_and_checked(self) -> None:
        customer = make_customer()
        customer.vat_id = "de 123 456 789"
        customer.full_clean()
        customer.save()
        self.assertEqual(Customer.objects.get().vat_id, "DE123456789")
        customer.vat_id = "123456789"
        with self.assertRaises(ValidationError):
            customer.full_clean()

    def test_standard_discount_on_new_lines(self) -> None:
        customer = make_customer()
        customer.default_discount_percent = Decimal("10")
        customer.save()
        project = make_project(customer=customer)
        cable = make_product("K-005")
        self.assertEqual(add_line(project, cable, 2).line.discount_percent, Decimal("10.00"))
        self.assertEqual(add_line(project, cable, 1, discount_percent=Decimal("0")).line.discount_percent, 0)
        surcharge = make_product(
            "A-002", kind="surcharge", price=None, surcharge_type="percent", surcharge_percent=Decimal("10")
        )
        self.assertEqual(add_line(project, surcharge, 1).line.discount_percent, 0)


class DuplicateTests(RentalarsTestCase):
    """KND-008: a warning when a customer may exist already."""

    def test_names(self) -> None:
        self.assertEqual(normalised_name("Stadtwerke Musterstadt GmbH & Co. KG"), "stadtwerke musterstadt")
        self.assertEqual(normalised_name("Kulturverein e.V."), "kulturverein")
        existing = make_customer("Stadtwerke Musterstadt GmbH")
        make_customer("Stadtwerke Nordstadt")
        found = find_duplicates("stadtwerke  musterstadt")
        self.assertEqual([duplicate.customer for duplicate in found], [existing])
        self.assertEqual([d.customer for d in find_duplicates("Stadtwerke Musterstadt Veranstaltungen")], [existing])
        self.assertEqual(find_duplicates("Musterstadt Events"), [])
        self.assertEqual(find_duplicates("Stadtwerke Musterstadt", exclude_pk=existing.pk), [])

    def test_email_of_customer_or_contact(self) -> None:
        first = make_customer("Agentur Blau")
        first.email = "info@blau.example"
        first.save()
        second = make_customer("Messe GmbH")
        Contact.objects.create(customer=second, name="Eva", email="eva@messe.example")
        self.assertEqual([d.customer for d in find_duplicates("Neu", "INFO@blau.example")], [first])
        found = find_duplicates("Messe", "eva@messe.example")
        self.assertEqual(
            [(d.customer, str(d.reason)) for d in found], [(second, "ähnlicher Name und gleiche E-Mail-Adresse")]
        )


class QualificationTests(RentalarsTestCase):
    """PER-014: qualifications with expiry date and certificate."""

    def setUp(self) -> None:
        super().setUp()
        self.person = make_person("Anna Beispiel")
        self.first_aid = QualificationType.objects.create(name="Ersthelfer", validity_months=24)
        self.platform = QualificationType.objects.create(name="Hubarbeitsbühne (IPAF 3a)")

    def test_validity_from_the_type_and_state(self) -> None:
        qualification = save_qualification(
            Qualification(person=self.person, qualification_type=self.first_aid, acquired_on=datetime.date(2025, 4, 1)),
            document=pdf_file(),
        )
        self.assertEqual(qualification.valid_until, datetime.date(2027, 4, 1))
        self.assertEqual(qualification.state, "soon")
        self.assertTrue(qualification.document.name.startswith(f"qualifications/{self.person.pk}/"))
        self.assertEqual(qualification.document_name, "nachweis.pdf")
        endless = save_qualification(Qualification(person=self.person, qualification_type=self.platform))
        self.assertEqual((endless.valid_until, endless.state), (None, "valid"))

    def test_wrong_input_is_refused(self) -> None:
        save_qualification(Qualification(person=self.person, qualification_type=self.platform))
        with self.assertRaises(ValidationError):
            save_qualification(Qualification(person=self.person, qualification_type=self.platform))
        with self.assertRaises(ValidationError):
            save_qualification(
                Qualification(
                    person=self.person,
                    qualification_type=self.first_aid,
                    acquired_on=datetime.date(2027, 1, 1),
                    valid_until=datetime.date(2026, 1, 1),
                )
            )
        with self.assertRaises(ValidationError):
            save_qualification(
                Qualification(person=self.person, qualification_type=self.first_aid),
                document=SimpleUploadedFile("x.exe", b"MZ", "application/octet-stream"),
            )

    def test_reported_once_to_planning_and_the_person(self) -> None:
        planner = make_user("petra", roles=("Personaldisposition",))
        # AUT-026: the person has an account of its own already.
        User.objects.filter(pk=self.person.user_id).update(username="anna")
        save_qualification(
            Qualification(person=self.person, qualification_type=self.first_aid, valid_until=datetime.date(2027, 3, 20))
        )
        save_qualification(
            Qualification(person=self.person, qualification_type=self.platform, valid_until=datetime.date(2028, 1, 1))
        )
        self.assertEqual(check_expiring_qualifications(), 1)
        self.assertEqual(check_expiring_qualifications(), 0)
        kinds = Notification.objects.filter(kind=Kind.QUALIFICATION_EXPIRY)
        self.assertEqual(sorted(kinds.values_list("user__username", flat=True)), ["anna", "petra"])
        self.assertIn("20.03.2027", kinds.first().title)
        self.assertTrue(planner.pk)

    def test_privacy(self) -> None:
        qualification = save_qualification(
            Qualification(person=self.person, qualification_type=self.platform, detail="3a, 3b"), document=pdf_file()
        )
        path = qualification.document.path
        self.assertEqual(export_person(self.person)["qualifications"][0]["details"], "3a, 3b")
        anonymise_person(self.person)
        self.assertFalse(Qualification.objects.exists())
        from pathlib import Path

        self.assertFalse(Path(path).exists())
        other = make_person("Bert Zwei")
        kept = save_qualification(
            Qualification(person=other, qualification_type=self.platform), document=pdf_file()
        ).document.path
        delete_person(other)
        self.assertFalse(Path(kept).exists())


class DueInspectionReportTests(RentalarsTestCase):
    """MAT-032: one notification per run for the inspections that became due."""

    def test_reported_once(self) -> None:
        warehouse = make_user("luka", roles=("Lager",))
        model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        make_items(model, 3)
        electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        electric.categories.add(category("L"))
        self.assertEqual(report_due_inspections(), 3)
        self.assertEqual(report_due_inspections(), 0)
        notification = Notification.objects.get(user=warehouse, kind=Kind.INSPECTION_DUE)
        self.assertIn("3 Prüfungen fällig (3 überfällig)", notification.title)
        self.assertEqual(DueNotice.objects.count(), 3)


class TimelineTests(RentalarsTestCase):
    """VFG-019 for products, PER-020 for people; PRJ-067 the week of the calendar."""

    def test_product_timeline(self) -> None:
        product = make_stock("K-005", 4, "XLR-Kabel")
        visible = make_project("Sichtbar", start=at(2), end=at(4))
        hidden = make_project("Geheim", start=at(3), end=at(5))
        add_line(visible, product, 3)
        add_line(hidden, product, 1)
        days = [datetime.date(2027, 3, day) for day in range(1, 8)]
        timeline = product_timeline(product, days, {visible.pk})
        free = [load.free for load in timeline.rows[0].loads]
        self.assertEqual(free, [4, 1, 0, 3, 4, 4, 4])
        labels = [row.label for row in timeline.rows[1:]]
        self.assertEqual(labels, [f"{visible.number} Sichtbar", hidden.number])
        self.assertEqual(timeline.rows[1].bars[0].label, "3×")

    def test_person_timeline(self) -> None:
        person = make_person("Anna Beispiel")
        sound = job_function("Tontechnik")
        visible = make_project("Sichtbar", start=at(2, 8), end=at(3, 18))
        hidden = make_project("Geheim", start=at(5, 8), end=at(5, 18))
        plan(visible, sound, person)
        plan(hidden, sound, person)
        Qualification.objects.create(
            person=person,
            qualification_type=QualificationType.objects.create(name="Ersthelfer"),
            valid_until=datetime.date(2027, 3, 6),
        )
        days = [datetime.date(2027, 3, day) for day in range(1, 8)]
        timeline = person_timeline(person, days, {visible.pk})
        bars = timeline.rows[0].bars
        self.assertEqual(
            [bar.label for bar in bars], [f"{visible.number} Sichtbar · Tontechnik", f"{hidden.number} · Tontechnik"]
        )
        self.assertEqual((bars[0].url, bars[1].url), (f"/projects/{visible.number}/overview/", ""))
        self.assertEqual(timeline.rows[2].bars[0].label, "Ersthelfer läuft ab")

    def test_week_of_the_calendar(self) -> None:
        project = make_project("Stadtfest", start=at(2, 8), end=at(4, 18))
        days = week_calendar(type(project).objects.all(), datetime.date(2027, 3, 1))
        times = [[entry.times for entry in day.entries] for day in days]
        self.assertEqual(times[:5], [[], ["ab 08:00"], ["ganztägig"], ["bis 18:00"], []])
