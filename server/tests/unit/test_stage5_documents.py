# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the documents of stage 5: DOK-003, DOK-004, DOK-005, DOK-006, DOK-007, DOK-008, DOK-009."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.core.models import CompanyProfile
from rentalars.documents import services
from rentalars.documents.models import Document, DocumentKind, DocumentTemplate, TextBlock
from rentalars.documents.xrechnung import NAMESPACES
from rentalars.projects.models import GroupKind
from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_pdf
from rentalars.projects.services import update_group
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
    ready_for_invoices,
)


class DocumentTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        customer = ready_for_invoices()
        customer.payment_terms_days = 30
        customer.save()
        self.project = make_project("Stadtfest", customer=customer, start=at(10, 8), end=at(12, 18))
        self.group = add_group(self.project, "Licht")
        add_line(self.project, make_stock("L-010", 6, "PAR 64", price="20.00"), 4, group=self.group)
        add_line(self.project, make_stock("K-005", 10, price="2.50"), 6)
        self.user = make_user("luka")

    def test_invoice_with_xrechnung(self) -> None:
        update_group(self.group, rights=ALL_RIGHTS, discount_percent=Decimal("10"))
        invoice = services.create_document(self.project, DocumentKind.INVOICE, user=self.user)
        self.assertEqual(invoice.number, "RE-2027-0001")
        self.assertTrue(invoice.file.read().startswith(b"%PDF"))
        self.assertTrue(services.verify(invoice))
        self.assertEqual(invoice.due_on.isoformat(), "2027-03-31")
        # 3 rental days, factor 1,75 of the standard scale (ADM-011): 4 × 20,00 × 1,75 = 140,00 − 10 % = 126,00;
        # 6 × 2,50 × 1,75 = 26,25
        self.assertEqual((invoice.net_total, invoice.gross_total), (Decimal("152.25"), Decimal("181.18")))
        root = ET.fromstring(invoice.xml_file.read())
        cbc = "{" + NAMESPACES["cbc"] + "}"
        self.assertEqual(root.find(f"{cbc}ID").text, "RE-2027-0001")
        totals = root.find("{" + NAMESPACES["cac"] + "}LegalMonetaryTotal")
        values = {child.tag.split("}")[1]: child.text for child in totals}
        self.assertEqual(values["LineExtensionAmount"], "166.25")
        self.assertEqual(values["AllowanceTotalAmount"], "14.00")
        self.assertEqual(values["TaxExclusiveAmount"], "152.25")
        self.assertEqual(values["PayableAmount"], "181.18")
        self.assertEqual(len(root.findall("{" + NAMESPACES["cac"] + "}InvoiceLine")), 2)

    def test_second_invoice_needs_a_cancellation(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        with self.assertRaises(ValidationError):
            services.create_document(self.project, DocumentKind.INVOICE)
        cancellation = services.cancel_invoice(invoice)
        invoice.refresh_from_db()
        self.assertEqual(
            (cancellation.number, cancellation.cancels, invoice.cancelled_by), ("RE-2027-0002", invoice, cancellation)
        )
        self.assertEqual(cancellation.gross_total, -invoice.gross_total)
        root = ET.fromstring(cancellation.xml_file.read())
        self.assertEqual(root.find("{" + NAMESPACES["cbc"] + "}InvoiceTypeCode").text, "384")
        with self.assertRaises(ValidationError):
            services.cancel_invoice(invoice)
        self.assertEqual(services.create_document(self.project, DocumentKind.INVOICE).number, "RE-2027-0003")

    def test_documents_never_change(self) -> None:
        document = services.create_document(self.project, DocumentKind.ORDER_CONFIRMATION)
        document.title = "anders"
        with self.assertRaises(ValidationError):
            document.save()
        with self.assertRaises(ValidationError):
            document.delete()
        services.mark_sent(document, "a@b.example")
        self.assertEqual(Document.objects.get().sent_to, "a@b.example")

    def test_invoice_needs_company_data(self) -> None:
        CompanyProfile.objects.update(email="", phone="-")
        with self.assertRaises(ValidationError) as caught:
            services.create_document(self.project, DocumentKind.INVOICE)
        self.assertIn("E-Mail-Adresse der Firma, Telefonnummer der Firma", str(caught.exception))
        self.assertFalse(Document.objects.exists())

    def test_a_cancellation_names_the_company_as_it_is_now(self) -> None:
        """The XRechnung of a cancellation needs complete company data of today; no number is used up without."""
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        CompanyProfile.objects.update(phone="")
        with self.assertRaises(ValidationError):
            services.cancel_invoice(invoice)
        CompanyProfile.objects.update(phone="040 9876543", name="Licht & Ton GmbH & Co. KG")
        cancellation = services.cancel_invoice(invoice)
        self.assertEqual(cancellation.number, "RE-2027-0002")
        self.assertEqual(cancellation.content["company"]["name"], "Licht & Ton GmbH & Co. KG")
        self.assertIn(b"040 9876543", cancellation.xml_file.read())

    def test_texts_and_text_blocks(self) -> None:
        template = DocumentTemplate.objects.get(kind=DocumentKind.ORDER_CONFIRMATION)
        template.introduction = "Projekt {project} für {customer}, {unbekannt}."
        template.save()
        block = TextBlock.objects.create(
            name="Mietbedingungen", text="Es gelten unsere Mietbedingungen.", kinds=["order_confirmation"]
        )
        content = services.build_content(
            self.project, DocumentKind.ORDER_CONFIRMATION, number="X", issued_on=at(1).date(), text_block_ids=[block.pk]
        )
        self.assertEqual(
            content.introduction, f"Projekt {self.project.number} für Stadtwerke Musterstadt, {{unbekannt}}."
        )
        self.assertEqual(content.text_blocks, ["Es gelten unsere Mietbedingungen."])
        self.assertEqual(services.text_blocks_for(DocumentKind.INVOICE), [])

    def test_delivery_note_and_crew_sheet(self) -> None:
        delivery = services.create_document(self.project, DocumentKind.DELIVERY_NOTE)
        self.assertEqual(delivery.number, "LS-2027-0001")
        self.assertIsNone(delivery.net_total)
        self.assertEqual([row["article_number"] for row in delivery.content["delivery_rows"][0][1]], ["L-010", "K-005"])
        with self.assertRaises(ValidationError):
            services.create_document(self.project, DocumentKind.CREW_SHEET)
        anna = make_person("Anna Beispiel", rates={"Tontechnik": "35.00"})
        anna.phone, anna.share_phone = "0170 1", True
        anna.save()
        plan(self.project, job_function("Tontechnik"), anna, start=at(10, 8), end=at(10, 18))
        sheet = services.create_document(self.project, DocumentKind.CREW_SHEET)
        row = sheet.content["crew_rows"][0]
        self.assertEqual((row["person"], row["phone"], row["email"]), ("Anna Beispiel", "0170 1", ""))
        self.assertNotIn("35", str(sheet.content["crew_rows"]))

    def test_optional_groups_stay_off_the_invoice(self) -> None:
        """An optional group shows on the order confirmation, not on the invoice."""
        update_group(self.group, rights=ALL_RIGHTS, kind=GroupKind.OPTIONAL)
        confirmation = services.build_content(
            self.project, DocumentKind.ORDER_CONFIRMATION, number="X", issued_on=at(1).date()
        )
        invoice = services.build_content(self.project, DocumentKind.INVOICE, number="Y", issued_on=at(1).date())
        self.assertEqual([section.optional for section in confirmation.sections], [True, False])
        self.assertEqual([section.title for section in invoice.sections], ["Ohne Teilgruppe"])
        self.assertEqual(invoice.sections[0].positions[0].number, "1")
        self.assertEqual(invoice.net_total, Decimal("26.25"))  # 6 × 2,50 × 1,75 (ADM-011)

    def test_leitweg_id_and_text_blocks_per_kind(self) -> None:
        customer = self.project.customer
        customer.buyer_reference = "04011000-1234512345-06"
        customer.save()
        block = TextBlock.objects.create(name="Bedingungen", text="Nur für Rechnungen.", kinds=["invoice"])
        note = services.build_content(
            self.project, DocumentKind.DELIVERY_NOTE, number="X", issued_on=at(1).date(), text_block_ids=[block.pk]
        )
        self.assertEqual(note.text_blocks, [])
        invoice = services.create_document(self.project, DocumentKind.INVOICE, text_block_ids=[block.pk])
        self.assertEqual(invoice.content["text_blocks"], ["Nur für Rechnungen."])
        root = ET.fromstring(invoice.xml_file.read())
        self.assertEqual(root.find("{" + NAMESPACES["cbc"] + "}BuyerReference").text, "04011000-1234512345-06")

    def test_crew_sheets_count_on_their_own(self) -> None:
        anna = make_person("Anna Beispiel")
        plan(self.project, job_function("Tontechnik"), anna, start=at(10, 8), end=at(10, 18))
        self.assertEqual(services.create_document(self.project, DocumentKind.CREW_SHEET).number, "CD-2027-0001")

    def test_preview_counts_nothing(self) -> None:
        self.assertTrue(services.preview(self.project, DocumentKind.INVOICE).startswith(b"%PDF"))
        self.assertFalse(Document.objects.exists())
        self.assertEqual(services.create_document(self.project, DocumentKind.INVOICE).number, "RE-2027-0001")


class PriceOverviewFileTests(RentalarsTestCase):
    """DOK-009: the price overview as PDF and CSV."""

    def test_pdf_and_csv(self) -> None:
        project = make_project()
        add_line(project, make_product("L-010", "PAR 64", price="20.00"), 4)
        self.assertTrue(render_price_overview_pdf(project, with_lines=True).startswith(b"%PDF"))
        lines = render_price_overview_csv(project).lstrip("﻿").splitlines()
        self.assertEqual(lines[0].split(";")[:3], ["Bereich", "Art.-Nr.", "Name"])
        self.assertIn("PAR 64", lines[1])
        self.assertTrue(lines[-1].startswith("Summe brutto"))
        groups = render_price_overview_csv(project, with_lines=False).lstrip("﻿").splitlines()
        self.assertEqual(len(groups[0].split(";")), 3)
