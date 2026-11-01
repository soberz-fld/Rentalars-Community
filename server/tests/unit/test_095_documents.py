# SPDX-License-Identifier: GPL-3.0-or-later
"""Product descriptions in documents (DOK-020 and others) and outgoing documents without a project.

The requirement: it can be chosen whether the description of the products is printed in the documents (quotes,
invoices, ...).

* The template of each kind says whether the description of the products is printed; the default is not to print it.
  The dialog "Make a document" presets the box from it and the document stores the choice.
* The choice reaches every renderer: PDF, the electronic invoice (BT-154), the draft, the mail. A line's own text
  is never dropped. DATEV does not read descriptions.

The requirement: quotes, invoices, ... can be made independently of projects and service cases, e.g. by a button
"Neuer Ausgangsbeleg" in Buchhaltung → Ausgangsbelege that opens a pop-up.

* A document without a project: dialog → draft → lines → issue; the number comes from the shared range.
* PDF, XRechnung, DATEV, cancellation, the list with its filter, the page of the customer, rights, the API.
"""

from __future__ import annotations

import datetime
import html
import io
import json
import re
from decimal import Decimal
from typing import Any
from unittest import mock
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse

from rentalars.accounts.rights import ProjectScope, rights_of
from rentalars.core.models import SystemSettings
from rentalars.customers import services as customer_services
from rentalars.documents import content as builder
from rentalars.documents import datev, free, services
from rentalars.documents.models import (
    FREE_KINDS,
    AccountingSettings,
    Document,
    DocumentDraft,
    DocumentKind,
    DocumentTemplate,
    DraftLine,
)
from rentalars.documents.xrechnung import NAMESPACES
from rentalars.masterdata.models import TaxRate
from rentalars.products.models import BillingMode
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    add_line,
    make_customer,
    make_product,
    make_project,
    ready_for_invoices,
)
from tests.mailbox import capture_smtp, configure_mailbox
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_091_accounting import numbers_of, role

D = Decimal
OUTGOING = "/accounting/documents/"
NEW = "/accounting/documents/new/"


def pdf_text(response: Any) -> str:
    """The text of a PDF answer."""
    content = b"".join(response.streaming_content) if hasattr(response, "streaming_content") else response.content
    return pdf_words(content)


def pdf_words(content: bytes) -> str:
    """The text of PDF bytes with every run of white space as one blank (the PDF breaks lines where it likes)."""
    from pypdf import PdfReader

    return " ".join("".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages).split())


def flat(article_number: str, name: str, price: str, **fields: Any) -> Any:
    """A product billed as a flat price: quantity × price."""
    return make_product(article_number, name, price=price, billing_mode=BillingMode.FLAT, **fields)


DESCRIPTION = "Zwei Tops, zwei Subs und Stative inklusive"
OWN_TEXT = "Aufbau ab 14 Uhr"
OWN_NOTE = "Zufahrt über Tor 2"


def xml_of(document: Document) -> ElementTree.Element:
    """The parsed XRechnung of a document."""
    with document.xml_file.open("rb") as handle:
        return ElementTree.fromstring(handle.read())


def bt154(document: Document) -> list[str]:
    """BT-154 of every invoice line of the XRechnung: the item descriptions."""
    path = "cac:InvoiceLine/cac:Item/cbc:Description"
    return [element.text or "" for element in xml_of(document).findall(path, NAMESPACES)]


def stored_pdf(document: Document) -> str:
    """The text of the PDF stored with a document."""
    with document.file.open("rb") as handle:
        return pdf_words(handle.read())


class DescriptionData:
    """A project with a product that has a description, one that has none, and a text line of its own."""

    def build(self) -> None:
        self.customer = ready_for_invoices(make_customer("Bühnenwerk Köln"))
        self.pa = flat("L-100", "PA-Anlage", "100.00", description=DESCRIPTION)
        self.cable = flat("K-100", "Kabel", "5.00")
        self.project = make_project("Sommerfest", customer=self.customer)
        add_line(self.project, self.pa, 2)
        add_line(self.project, self.cable, 4)
        from rentalars.projects import services as project_services

        project_services.add_text_line(self.project, title=OWN_TEXT, note=OWN_NOTE)


class DescriptionCase(DescriptionData, UiTestCase):
    """The data of :class:`DescriptionData` for the tests of the pages."""

    def setUp(self) -> None:
        super().setUp()
        self.build()

    def template(self, kind: str, **fields: Any) -> DocumentTemplate:
        """The template of a kind with some fields changed."""
        template = services.template_for(kind)
        for name, value in fields.items():
            setattr(template, name, value)
        template.save()
        return template


class DescriptionSettingTests(DescriptionCase):
    """The template of each kind holds the default; by default nothing is printed."""

    def test_the_default_keeps_the_behaviour_of_094(self) -> None:
        for kind in DocumentKind.values:
            self.assertFalse(services.template_for(kind).print_product_descriptions, kind)
        document = services.create_document(self.project, DocumentKind.OFFER, user=self.admin_user)
        self.assertFalse(document.print_product_descriptions)
        self.assertNotIn(DESCRIPTION, stored_pdf(document))
        self.assertTrue(all(not p["description"] for s in document.content["sections"] for p in s["positions"]))

    def test_the_template_decides_and_the_call_may_overrule_it(self) -> None:
        self.template(DocumentKind.OFFER, print_product_descriptions=True)
        by_default = services.create_document(self.project, DocumentKind.OFFER)
        self.assertTrue(by_default.print_product_descriptions)
        self.assertIn(DESCRIPTION, stored_pdf(by_default))
        overruled = services.create_document(self.project, DocumentKind.OFFER, print_product_descriptions=False)
        self.assertFalse(overruled.print_product_descriptions)
        self.assertNotIn(DESCRIPTION, stored_pdf(overruled))
        # The other kinds keep their own default.
        self.assertFalse(
            services.create_document(self.project, DocumentKind.ORDER_CONFIRMATION).print_product_descriptions
        )

    def test_the_dialog_is_preset_from_the_template_and_stores_the_choice(self) -> None:
        self.template(DocumentKind.INVOICE, print_product_descriptions=True)
        url = reverse("documents:list", args=[self.project.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Beschreibung der Produkte mitdrucken", page)
        defaults = json.loads(html.unescape(re.search(r'data-description-defaults="([^"]*)"', page)[1]))
        self.assertEqual(defaults["invoice"], True)
        self.assertEqual(defaults["offer"], False)
        # The box is preset for the kind shown first; the page script follows the kind.
        data = form_data(self.client.get(url), containing="valid_until", kind="offer")
        self.assertNotIn("print_product_descriptions", data)
        invoice = form_data(self.client.get(url + "?kind=invoice"), containing="valid_until", kind="invoice")
        self.assertEqual(invoice.get("print_product_descriptions"), "on")
        # Ticked: stored with the document; cleared although the template says yes: not printed.
        self.client.post(
            reverse("documents:create", args=[self.project.pk]), {**data, "print_product_descriptions": "on"}
        )
        self.assertTrue(Document.objects.get(kind="offer").print_product_descriptions)
        Document.objects.all().delete()
        self.client.post(
            reverse("documents:create", args=[self.project.pk]), {**invoice, "print_product_descriptions": ""}
        )
        self.assertFalse(Document.objects.get(kind="invoice").print_product_descriptions)

    def test_a_crew_disposition_has_no_products_and_no_choice(self) -> None:
        from rentalars.documents.admin import DocumentTemplateAdmin

        admin = DocumentTemplateAdmin(DocumentTemplate, mock.Mock())
        crew = services.template_for(DocumentKind.CREW_SHEET)
        self.assertIn("print_product_descriptions", admin.get_exclude(mock.Mock(), crew))
        self.assertNotIn("print_product_descriptions", admin.get_exclude(mock.Mock(), services.template_for("offer")))


class DescriptionRendererTests(DescriptionCase):
    """The choice reaches the PDF, the electronic invoice, the draft and the mail; DATEV does not read it."""

    def made(self, kind: str, printed: bool) -> Document:
        return services.create_document(self.project, kind, user=self.admin_user, print_product_descriptions=printed)

    def test_pdf(self) -> None:
        for printed in (True, False):
            with self.subTest(printed=printed):
                text = stored_pdf(self.made(DocumentKind.ORDER_CONFIRMATION, printed))
                self.assertEqual(DESCRIPTION in text, printed)
                # The line's own text is never dropped.
                self.assertIn("PA-Anlage", text)
                self.assertIn(OWN_TEXT, text)
                self.assertIn(OWN_NOTE, text)

    def test_the_description_of_a_product_without_one_prints_nothing(self) -> None:
        document = self.made(DocumentKind.OFFER, True)
        descriptions = [p["description"] for s in document.content["sections"] for p in s["positions"] if p["title"]]
        self.assertEqual([d for d in descriptions if d], [DESCRIPTION])

    def test_xrechnung_bt_154(self) -> None:
        printed = self.made(DocumentKind.INVOICE, True)
        self.assertIn(DESCRIPTION, " ".join(bt154(printed)))
        # The calculation notes of the position stay in BT-154 in any case.
        Document.objects.all().delete()
        plain = self.made(DocumentKind.INVOICE, False)
        self.assertNotIn(DESCRIPTION, " ".join(bt154(plain)))
        self.assertEqual(len(xml_of(plain).findall("cac:InvoiceLine", NAMESPACES)), 2)

    def test_the_draft_pdf(self) -> None:
        for printed in (True, False):
            pdf = services.preview(
                self.project, DocumentKind.OFFER, user=self.admin_user, print_product_descriptions=printed
            )
            self.assertEqual(DESCRIPTION in pdf_words(pdf), printed)
        template_default = services.preview(self.project, DocumentKind.OFFER, user=self.admin_user)
        self.assertNotIn(DESCRIPTION, pdf_words(template_default))
        self.template(DocumentKind.OFFER, print_product_descriptions=True)
        self.assertIn(DESCRIPTION, pdf_words(services.preview(self.project, DocumentKind.OFFER, user=self.admin_user)))

    def test_the_delivery_note(self) -> None:
        for printed in (True, False):
            note = services.create_document(
                self.project, DocumentKind.DELIVERY_NOTE, print_product_descriptions=printed
            )
            self.assertEqual(DESCRIPTION in stored_pdf(note), printed, printed)
            self.assertIn("PA-Anlage", stored_pdf(note))

    def test_the_crew_disposition_never_prints_them(self) -> None:
        content = services.build_content(
            self.project, DocumentKind.CREW_SHEET, number="X", issued_on=datetime.date(2027, 3, 1),
            print_product_descriptions=True,
        )  # fmt: skip
        self.assertFalse(content.print_product_descriptions)

    def test_a_cancellation_repeats_its_invoice(self) -> None:
        for printed in (True, False):
            Document.objects.all().update(cancelled_by=None)
            Document.objects.filter(cancels__isnull=False).delete()
            Document.objects.all().delete()
            invoice = self.made(DocumentKind.INVOICE, printed)
            cancellation = services.cancel_invoice(invoice, user=self.admin_user)
            self.assertEqual(cancellation.print_product_descriptions, printed)
            self.assertEqual(DESCRIPTION in stored_pdf(cancellation), printed)
            self.assertEqual(DESCRIPTION in " ".join(bt154(cancellation)), printed)

    def test_the_mail_carries_the_stored_pdf(self) -> None:
        from rentalars.mail.sending import chosen_attachments

        for printed in (True, False):
            document = self.made(DocumentKind.OFFER, printed)
            (attachment,) = chosen_attachments(self.project, rights=ALL_RIGHTS, documents=[f"doc:{document.pk}"])
            self.assertEqual(DESCRIPTION in pdf_words(attachment.data), printed)
            with document.file.open("rb") as handle:
                self.assertEqual(attachment.data, handle.read())

    def test_datev_does_not_read_descriptions(self) -> None:
        accounting = AccountingSettings.load()
        accounting.datev_consultant_number, accounting.datev_client_number = 29098, 55003
        accounting.save()
        outcomes = []
        for printed in (True, False):
            Document.objects.all().delete()
            self.made(DocumentKind.INVOICE, printed)
            result = datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))
            # Without the time stamp of the header the file is the same.
            text = result.content.decode("cp1252").split("\r\n", 1)[1]
            outcomes.append(re.sub(r"RE-2027-\d{4}", "RE", text))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertIn("Rechnung RE", outcomes[0])

    def test_the_stored_content_is_what_is_rendered(self) -> None:
        """One rule serves every renderer: the content has the descriptions or has not."""
        printed = self.made(DocumentKind.OFFER, True)
        self.assertTrue(printed.content["print_product_descriptions"])
        plain = self.made(DocumentKind.OFFER, False)
        self.assertFalse(plain.content["print_product_descriptions"])
        stripped = builder.strip_descriptions(
            services.build_content(
                self.project,
                DocumentKind.OFFER,
                number="",
                issued_on=datetime.date(2027, 3, 1),
                print_product_descriptions=True,
            )
        )
        self.assertTrue(all(not p.description for s in stripped.sections for p in s.positions))
        self.assertIn(OWN_NOTE, [p.details for s in stripped.sections for p in s.positions])


class DescriptionApiTests(DescriptionData, ApiTestCase):
    """``print_product_descriptions`` on the create endpoint, the document and the template."""

    def setUp(self) -> None:
        super().setUp()
        self.build()
        self.url = f"{API}/projects/{self.project.pk}/documents"

    def test_create_with_the_choice(self) -> None:
        printed = self.admin.post(self.url, {"kind": "offer", "print_product_descriptions": True}, format="json")
        self.assertEqual(printed.status_code, 201, printed.content)
        self.assertTrue(printed.json()["print_product_descriptions"])
        self.assertIn(DESCRIPTION, stored_pdf(Document.objects.get(pk=printed.json()["id"])))
        plain = self.admin.post(self.url, {"kind": "offer", "print_product_descriptions": False}, format="json")
        self.assertFalse(plain.json()["print_product_descriptions"])
        # Left out or null: as the template says.
        default = self.admin.post(self.url, {"kind": "offer", "print_product_descriptions": None}, format="json")
        self.assertFalse(default.json()["print_product_descriptions"])
        self.assertFalse(self.admin.get(f"{API}/documents/{default.json()['id']}").json()["print_product_descriptions"])

    def test_the_template_sets_the_default(self) -> None:
        templates = {entry["kind"]: entry for entry in self.admin.get(f"{API}/document-templates").json()}
        self.assertFalse(templates["offer"]["print_product_descriptions"])
        changed = self.admin.patch(
            f"{API}/document-templates/{templates['offer']['id']}", {"print_product_descriptions": True}, format="json"
        )
        self.assertTrue(changed.json()["print_product_descriptions"])
        offer = self.admin.post(self.url, {"kind": "offer"}, format="json").json()
        self.assertTrue(offer["print_product_descriptions"])

    def test_the_draft_follows_the_choice(self) -> None:
        pdf = self.admin.post(
            f"{self.url}/preview", {"kind": "offer", "print_product_descriptions": True}, format="json"
        )
        self.assertIn(DESCRIPTION, pdf_words(pdf.content))
        pdf = self.admin.post(f"{self.url}/preview", {"kind": "offer"}, format="json")
        self.assertNotIn(DESCRIPTION, pdf_words(pdf.content))


# --- Documents without a project ----------------------------------------------------------------------------


class FreeData:
    """A customer ready for invoices, two products (one with a description) and a second tax rate."""

    def build(self) -> None:
        self.customer = ready_for_invoices(make_customer("Bühnenwerk Köln"))
        self.pa = flat("L-100", "PA-Anlage", "100.00", description=DESCRIPTION)
        self.cable = flat("K-100", "Kabel", "5.00")
        self.rate = TaxRate.get_default()
        self.seven = TaxRate.objects.create(name="7 %", rate=D("7.00"))

    def make_draft(self, kind: str = DocumentKind.INVOICE, **fields: Any) -> DocumentDraft:
        """A draft with a free line (2 × 50,00) and a product line (3 × 100,00): net 400,00, gross 476,00."""
        draft = free.create_draft(self.customer, kind, user=self.admin_user, **fields)
        free.add_line(draft, title="Aufbau", quantity=D("2"), unit_price=D("50.00"))
        free.add_line(draft, product=self.pa, quantity=D("3"))
        return draft

    def issue(self, kind: str = DocumentKind.INVOICE, **fields: Any) -> Document:
        """A free document issued at once."""
        return free.issue(self.make_draft(kind, **fields), user=self.admin_user)


class FreeCase(FreeData, UiTestCase):
    """The data of :class:`FreeData` for the tests of the pages."""

    def setUp(self) -> None:
        super().setUp()
        self.build()


class FreeDialogTests(FreeCase):
    """The dialog "Neuer Ausgangsbeleg" and the page of the draft."""

    def test_the_button_and_the_dialog(self) -> None:
        page = self.assert_ok(self.client.get(OUTGOING))
        self.assertIn("Neuer Ausgangsbeleg", page)
        self.assertIn(f'hx-get="{NEW}"', page)
        dialog = self.assert_ok(self.htmx("get", NEW))
        self.assertIn('hx-post="/accounting/documents/new/"', dialog)
        for name in ("kind", "customer", "issued_on", "reference", "print_product_descriptions"):
            self.assertIn(f'name="{name}"', dialog)
        # The kinds: offer, order confirmation, invoice – no delivery note, cancellation or crew disposition.
        self.assertEqual(re.findall(r'<option value="(\w+)"', dialog.split('name="kind"')[1].split("</select>")[0]),
                         ["offer", "order_confirmation", "invoice"])  # fmt: skip

    def test_the_page_without_the_script(self) -> None:
        page = self.assert_ok(self.client.get(NEW))
        self.assertIn("<h1>Neuer Ausgangsbeleg</h1>", page)
        response = self.client.post(NEW, {"kind": "offer", "customer": self.customer.pk})
        draft = DocumentDraft.objects.get()
        self.assertRedirects(response, f"/accounting/documents/drafts/{draft.pk}/")

    def test_dialog_to_draft_to_document(self) -> None:
        response = self.htmx(
            "post",
            NEW,
            {"kind": "invoice", "customer": self.customer.pk, "reference": "Sommerfest 2027", "dependants_for": ""},
        )
        self.assertEqual(response.status_code, 204, response.content.decode()[:400])
        draft = DocumentDraft.objects.get()
        self.assertEqual(response["HX-Redirect"], f"/accounting/documents/drafts/{draft.pk}/")
        self.assertEqual(
            (draft.customer, draft.reference, draft.print_product_descriptions),
            (self.customer, "Sommerfest 2027", False),
        )
        edit = f"/accounting/documents/drafts/{draft.pk}/"
        self.assertIn("Sommerfest 2027", self.assert_ok(self.client.get(edit)))
        free_line = {
            "mode": "free",
            "title": "Aufbau",
            "quantity": "2",
            "unit_price": "50,00",
            "tax_rate": self.rate.pk,
        }
        self.client.post(f"{edit}lines/add/", free_line)
        self.client.post(f"{edit}lines/add/", {"mode": "product", "product": self.pa.pk, "quantity": "3"})
        self.client.post(f"{edit}lines/add/", {"mode": "text", "title": "Danke", "note": ""})
        self.assertEqual(
            [(line.title, line.quantity, line.unit_price, line.is_text) for line in draft.lines.all()],
            [("Aufbau", D("2"), D("50.00"), False), ("PA-Anlage", D("3"), D("100.00"), False), ("Danke", D("1"), D("0"), True)],
        )  # fmt: skip
        self.assertIn("400,00", self.assert_ok(self.client.get(edit)))
        issued = self.client.post(f"{edit}issue/")
        document = Document.objects.get()
        self.assertEqual(issued["Location"], f"/accounting/documents/{document.pk}/")
        self.assertEqual(
            (document.project, document.customer, document.gross_total), (None, self.customer, D("476.00"))
        )
        self.assertFalse(DocumentDraft.objects.exists())
        self.assertIn(document.number, self.assert_ok(self.client.get(issued["Location"])))
        self.assertIn("Aufbau", pdf_text(self.client.get(reverse("documents:file", args=[document.pk]))))

    def test_the_billing_address_and_contact_follow_the_customer(self) -> None:
        from rentalars.customers.models import AddressKind, Contact, CustomerAddress

        contact = Contact.objects.create(
            customer=self.customer, first_name="Berta", last_name="Berg", email="b@b.example"
        )
        address = CustomerAddress.objects.create(
            customer=self.customer, kind=AddressKind.BILLING, name="Buchhaltung", street="Hafen 2", postal_code="12345", city="Köln"
        )  # fmt: skip
        refreshed = self.assert_ok(self.htmx("get", NEW, {"customer": self.customer.pk, "kind": "offer"}))
        self.assertIn("Berta Berg", refreshed)
        self.assertIn("Hafen 2", refreshed)
        response = self.htmx(
            "post",
            NEW,
            {"kind": "offer", "customer": self.customer.pk, "dependants_for": self.customer.pk,
             "contact": contact.pk, "billing_address": address.pk},
        )  # fmt: skip
        self.assertEqual(response.status_code, 204)
        draft = DocumentDraft.objects.get()
        self.assertEqual((draft.contact, draft.billing_address), (contact, address))
        free.add_line(draft, title="Aufbau", quantity=D("1"), unit_price=D("50.00"))
        document = free.issue(draft)
        self.assertIn("Buchhaltung", " ".join(document.content["recipient"]))
        # The contact of another customer is not offered and not accepted.
        other = Contact.objects.create(customer=make_customer("Anderer"), first_name="Otto", last_name="Fremd")
        refused = self.htmx(
            "post",
            NEW,
            {"kind": "offer", "customer": self.customer.pk, "dependants_for": self.customer.pk, "contact": other.pk},
        )
        self.assertEqual(refused.status_code, 200)
        self.assertEqual(DocumentDraft.objects.count(), 0)

    def test_only_what_belongs_to_the_kind_is_taken(self) -> None:
        """The hidden fields of the other kinds are sent along but not kept."""
        self.htmx(
            "post",
            NEW,
            {"kind": "offer", "customer": self.customer.pk, "payment_terms_days": "10", "valid_until": "2027-04-01"},
        )
        draft = DocumentDraft.objects.get()
        self.assertEqual((draft.payment_terms_days, draft.valid_until), (None, datetime.date(2027, 4, 1)))


class FreeLineTests(FreeCase):
    """The line editor: free lines, lines from products, texts; discount, order, change, remove."""

    def setUp(self) -> None:
        super().setUp()
        self.draft = self.make_draft()
        self.edit = f"/accounting/documents/drafts/{self.draft.pk}/"

    def titles(self) -> list[str]:
        return [line.title for line in self.draft.lines.all()]

    def test_a_product_brings_its_price_unit_and_tax_rate(self) -> None:
        reduced = flat("S-100", "Programmheft", "10.00", tax_rate=self.seven)
        self.client.post(f"{self.edit}lines/add/", {"mode": "product", "product": reduced.pk, "quantity": "5"})
        line = self.draft.lines.get(product=reduced)
        self.assertEqual((line.title, line.quantity, line.unit_price, line.tax_rate, line.unit), ("Programmheft", D("5"), D("10.00"), self.seven, reduced.unit))  # fmt: skip

    def test_services_and_vehicles_are_no_lines_of_this_kind(self) -> None:
        vehicle = make_product(
            "V-100", "Transporter", price=None, kind="vehicle", vehicle_type="car", price_per_km=D("0.80")
        )
        response = self.client.post(
            f"{self.edit}lines/add/", {"mode": "product", "product": vehicle.pk, "quantity": "1"}, follow=True
        )
        self.assertEqual(self.draft.lines.count(), 2)
        self.assertIn("kann hier keine Zeile sein", self.assert_ok(response))

    def test_order_change_and_removal(self) -> None:
        first, second = self.draft.lines.all()
        self.client.post(f"{self.edit}lines/{first.pk}/move/", {"direction": "down"})
        self.assertEqual(self.titles(), ["PA-Anlage", "Aufbau"])
        self.client.post(f"{self.edit}lines/{first.pk}/move/", {"direction": "up"})
        self.assertEqual(self.titles(), ["Aufbau", "PA-Anlage"])
        # At the ends nothing happens.
        self.client.post(f"{self.edit}lines/{first.pk}/move/", {"direction": "up"})
        self.assertEqual(self.titles(), ["Aufbau", "PA-Anlage"])
        page = self.assert_ok(self.client.get(f"{self.edit}lines/{second.pk}/edit/"))
        self.assertIn("Zeile ändern", page)
        changed = self.client.post(
            f"{self.edit}lines/{second.pk}/edit/",
            form_data(
                self.client.get(f"{self.edit}lines/{second.pk}/edit/"), title="PA-Anlage groß", unit_price="120,00"
            ),
        )
        self.assertEqual(changed.status_code, 302)
        second.refresh_from_db()
        self.assertEqual((second.title, second.unit_price, second.product), ("PA-Anlage groß", D("120.00"), self.pa))
        self.client.post(f"{self.edit}lines/{first.pk}/delete/")
        self.assertEqual(self.titles(), ["PA-Anlage groß"])
        self.assertEqual([line.position for line in self.draft.lines.all()], [2])

    def test_discount_and_two_tax_rates(self) -> None:
        draft = free.create_draft(self.customer, DocumentKind.OFFER)
        free.add_line(draft, title="Technik", quantity=D("3"), unit_price=D("50.00"), discount_percent=D("10"))
        free.add_line(draft, title="Heft", quantity=D("10"), unit_price=D("10.00"), tax_rate=self.seven)
        calculation = free.calculate(free.lines_of(draft))
        self.assertEqual([line.amount for line in calculation.priced_lines], [D("135.00"), D("100.00")])
        self.assertEqual([(t.percent, t.net, t.tax) for t in calculation.taxes], [(D("19.00"), D("135.00"), D("25.65")), (D("7.00"), D("100.00"), D("7.00"))])  # fmt: skip
        self.assertEqual((calculation.net_total, calculation.tax_total, calculation.gross_total), (D("235.00"), D("32.65"), D("267.65")))  # fmt: skip
        page = self.assert_ok(self.client.get(f"/accounting/documents/drafts/{draft.pk}/"))
        self.assertIn("267,65", page)

    def test_a_refused_line_stays_on_the_page(self) -> None:
        bad = {"mode": "free", "title": "", "quantity": "1", "unit_price": "-5,00", "tax_rate": self.rate.pk}
        response = self.client.post(f"{self.edit}lines/add/", bad)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.draft.lines.count(), 2)
        self.assertIn("Dieses Feld ist zwingend erforderlich", response.content.decode())
        nothing = self.client.post(f"{self.edit}lines/add/", {"mode": "text", "title": ""}, follow=True)
        self.assertIn("Gib den Text ein", self.assert_ok(nothing))

    def test_a_text_line_has_no_amount(self) -> None:
        self.client.post(
            f"{self.edit}lines/add/", {"mode": "text", "title": "Zahlbar vor Ort", "note": "bar oder Karte"}
        )
        self.assertEqual(free.calculate(free.lines_of(self.draft)).net_total, D("400.00"))
        document = free.issue(self.draft)
        self.assertIn("Zahlbar vor Ort", stored_pdf(document))
        self.assertEqual(len(xml_of(document).findall("cac:InvoiceLine", NAMESPACES)), 2)

    def test_the_head_and_the_texts(self) -> None:
        page = self.client.get(self.edit)
        data = form_data(
            page,
            containing="introduction",
            reference="Sommerfest",
            introduction="Wie besprochen:",
            closing="Danke!",
        )
        data["payment_terms_days"] = "10"
        data["print_product_descriptions"] = "on"
        saved = self.client.post(self.edit, data)
        self.assertEqual(saved.status_code, 302, saved.content.decode()[:300])
        self.draft.refresh_from_db()
        self.assertEqual((self.draft.reference, self.draft.introduction, self.draft.closing, self.draft.payment_terms_days, self.draft.print_product_descriptions), ("Sommerfest", "Wie besprochen:", "Danke!", 10, True))  # fmt: skip
        document = free.issue(self.draft)
        text = stored_pdf(document)
        self.assertIn("Sommerfest", text)
        self.assertIn("Wie besprochen:", text)
        self.assertIn(DESCRIPTION, text)
        self.assertEqual(document.due_on, datetime.date(2027, 3, 11))

    def test_the_draft_pdf_uses_no_number(self) -> None:
        response = self.client.post(f"{self.edit}preview/")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("ENTWURF", pdf_text(response))
        self.assertFalse(Document.objects.exists())
        self.assertEqual(free.issue(self.draft).number, "RE-2027-0001")

    def test_a_draft_without_lines_cannot_be_looked_at_or_issued(self) -> None:
        empty = free.create_draft(self.customer, DocumentKind.OFFER)
        page = self.assert_ok(self.client.get(f"/accounting/documents/drafts/{empty.pk}/"))
        self.assertIn("Füge mindestens eine Zeile mit Preis hinzu", page)
        refused = self.client.post(f"/accounting/documents/drafts/{empty.pk}/issue/", follow=True)
        self.assertIn("Füge mindestens eine Zeile", self.assert_ok(refused))
        self.assertFalse(Document.objects.exists())

    def test_deleting_a_draft_uses_no_number(self) -> None:
        deleted = self.client.post(f"{self.edit}delete/")
        self.assertRedirects(deleted, OUTGOING)
        self.assertFalse(DocumentDraft.objects.exists() or DraftLine.objects.exists())
        self.assertEqual(self.issue().number, "RE-2027-0001")
        history = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk])))
        self.assertIn("Entwurf", history)


class FreeIssueTests(FreeCase):
    """Issuing: the shared numbers, the PDF, the electronic invoice, DATEV, Lexware Office, the mail, the cancellation."""

    def test_the_numbers_come_from_the_ranges_of_the_projects(self) -> None:
        project = make_project("Sommerfest", customer=self.customer)
        add_line(project, self.cable, 1)
        first = services.create_document(project, DocumentKind.INVOICE)
        offer = services.create_document(project, DocumentKind.OFFER)
        free_invoice = self.issue()
        free_offer = self.issue(DocumentKind.OFFER)
        confirmation = self.issue(DocumentKind.ORDER_CONFIRMATION)
        self.assertEqual(
            [first.number, offer.number, free_invoice.number, free_offer.number, confirmation.number],
            ["RE-2027-0001", "AN-2027-0001", "RE-2027-0002", "AN-2027-0002", "AB-2027-0001"],
        )
        # The cancellation shares the range of the invoices, too.
        cancellation = services.cancel_invoice(free_invoice)
        self.assertEqual(cancellation.number, "RE-2027-0003")
        self.assertEqual(services.create_document(project, DocumentKind.ORDER_CONFIRMATION).number, "AB-2027-0002")

    def test_the_document_as_stored(self) -> None:
        document = self.issue(reference="Sommerfest 2027")
        self.assertEqual(
            (document.project, document.customer, document.kind, document.title, document.number, document.reference),
            (None, self.customer, "invoice", "Rechnung", "RE-2027-0001", "Sommerfest 2027"),
        )
        self.assertEqual((document.net_total, document.gross_total), (D("400.00"), D("476.00")))
        self.assertEqual(document.issued_on, datetime.date(2027, 3, 1))
        self.assertEqual(document.due_on, datetime.date(2027, 3, 15))
        self.assertTrue(document.file.name.startswith("documents/free/"), document.file.name)
        self.assertTrue(document.xml_file)
        self.assertEqual(services.verify(document), True)
        self.assertEqual(document.created_by, self.admin_user)
        self.assertIn(
            "Rechnung RE-2027-0001",
            self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk]))),
        )

    def test_the_pdf(self) -> None:
        text = stored_pdf(self.issue(reference="Sommerfest 2027"))
        for expected in (
            "Rechnung",
            "RE-2027-0001",
            "Bühnenwerk Köln",
            "Sommerfest 2027",
            "Aufbau",
            "PA-Anlage",
            "Betrag",
            "476,00",
            "15.03.2027",
        ):
            self.assertIn(expected, text)
        self.assertNotIn(DESCRIPTION, text)
        self.assertNotIn("Projekt", text)

    def test_the_electronic_invoice(self) -> None:
        document = self.issue(reference="Sommerfest 2027")
        root = xml_of(document)
        text = lambda path: root.findtext(path, namespaces=NAMESPACES)  # noqa: E731
        self.assertEqual(text("cbc:ID"), "RE-2027-0001")
        self.assertEqual(text("cbc:DocumentCurrencyCode"), "EUR")
        self.assertEqual(text("cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount"), "400.00")
        self.assertEqual(text("cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"), "476.00")
        self.assertEqual(text("cac:LegalMonetaryTotal/cbc:PayableAmount"), "476.00")
        self.assertEqual(text("cac:TaxTotal/cbc:TaxAmount"), "76.00")
        # As for a project (buyer reference of the customer, else its number): the free text "Sommerfest 2027" is the
        # subject line and not a buyer reference.
        self.assertEqual(text("cbc:BuyerReference"), self.customer.number)
        self.assertEqual(len(root.findall("cac:InvoiceLine", NAMESPACES)), 2)
        other = self.issue()
        self.assertEqual(xml_of(other).findtext("cbc:BuyerReference", namespaces=NAMESPACES), self.customer.number)

    def test_an_offer_and_a_confirmation_have_no_electronic_invoice(self) -> None:
        offer = self.issue(DocumentKind.OFFER)
        self.assertFalse(offer.xml_file)
        self.assertEqual(offer.valid_until, datetime.date(2027, 3, 15))  # the 14 days of the template
        self.assertIsNone(offer.due_on)
        self.assertIn("gilt bis zum 15.03.2027", stored_pdf(offer))

    def test_datev_sums(self) -> None:
        accounting = AccountingSettings.load()
        accounting.datev_consultant_number, accounting.datev_client_number = 29098, 55003
        accounting.save()
        draft = free.create_draft(self.customer, DocumentKind.INVOICE)
        free.add_line(draft, title="Technik", quantity=D("3"), unit_price=D("50.00"), discount_percent=D("10"))
        free.add_line(draft, title="Heft", quantity=D("10"), unit_price=D("10.00"), tax_rate=self.seven)
        invoice = free.issue(draft)
        cancellation = services.cancel_invoice(invoice)
        result = datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))
        rows = [line.split(";") for line in result.content.decode("cp1252").removesuffix("\r\n").split("\r\n")][2:]
        debitor = self.customer.number
        self.assertEqual(
            [(row[0], row[1], row[6], row[7], row[10]) for row in rows],
            [
                ("160,65", '"S"', debitor, "8400", '"RE-2027-0001"'),
                ("107,00", '"S"', debitor, "8300", '"RE-2027-0001"'),
                ("160,65", '"H"', debitor, "8400", '"RE-2027-0002"'),
                ("107,00", '"H"', debitor, "8300", '"RE-2027-0002"'),
            ],
        )
        self.assertEqual(result.count, 4)
        self.assertEqual((invoice.gross_total, cancellation.gross_total), (D("267.65"), D("-267.65")))
        self.assertEqual(D("160.65") + D("107.00"), invoice.gross_total)
        # The debitor list names the customer although no project does.
        debitors = datev.debitors_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))
        self.assertIn("Bühnenwerk Köln".encode("cp1252"), debitors.content)

    def test_lexware_office(self) -> None:
        from rentalars.documents import lexware
        from tests.lexware_fake import FakeLexware

        invoice = self.issue(reference="Sommerfest 2027")
        with FakeLexware() as server:
            server.switch_on()
            first = lexware.request_transfer(invoice, user=self.admin_user)
            cancellation = services.cancel_invoice(invoice, user=self.admin_user)
            second = lexware.request_transfer(cancellation, user=self.admin_user)
        self.assertEqual((first.state, second.state), ("done", "done"), (first.error, second.error))
        voucher = server.vouchers[first.voucher_id]
        self.assertEqual((voucher["voucherNumber"], voucher["totalGrossAmount"], voucher["remark"]), ("RE-2027-0001", 476.0, "Sommerfest 2027 – Rentalars"))  # fmt: skip
        self.assertEqual(
            server.vouchers[second.voucher_id]["remark"], "Storno zu Rechnung RE-2027-0001. Sommerfest 2027 – Rentalars"
        )
        page = self.assert_ok(self.client.get(OUTGOING + f"?customer={self.customer.pk}"))
        self.assertIn("RE-2027-0001", page)

    def test_the_mail_with_the_pdf(self) -> None:
        configure_mailbox()
        document = self.issue()
        url = f"/accounting/documents/{document.pk}/send/"
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Anbei erhalten Sie unsere Rechnung", page)
        data = form_data(self.client.get(url), to="kasse@buehnenwerk.example", cc="", bcc="", xml="on")
        with capture_smtp() as sent:
            response = self.client.post(url, data)
        self.assertRedirects(response, f"/accounting/documents/{document.pk}/")
        (message,) = sent
        self.assertEqual(message["To"], "kasse@buehnenwerk.example")
        names = [part.get_filename() for part in message.iter_attachments()]
        self.assertEqual(names, ["Rechnung-RE-2027-0001.pdf", "RE-2027-0001.xml"])
        with document.file.open("rb") as handle:
            self.assertEqual(next(message.iter_attachments()).get_content(), handle.read())
        document.refresh_from_db()
        self.assertEqual(document.sent_to, "kasse@buehnenwerk.example")
        self.assertIsNotNone(document.sent_at)
        from rentalars.mail.models import MailLogEntry

        self.assertEqual(MailLogEntry.objects.get().recipients, "kasse@buehnenwerk.example")

    def test_the_mail_needs_a_mailbox_and_valid_addresses(self) -> None:
        document = self.issue()
        url = f"/accounting/documents/{document.pk}/send/"
        data = form_data(self.client.get(url), to="a@b.example")
        unset = self.client.post(url, data)
        self.assertEqual(unset.status_code, 200)
        self.assertIn("Der Versand ist nicht eingerichtet", unset.content.decode())
        configure_mailbox()
        with capture_smtp() as sent:
            wrong = self.client.post(url, {**data, "to": "kein-mail"})
        self.assertEqual((wrong.status_code, sent), (200, []))
        document.refresh_from_db()
        self.assertIsNone(document.sent_at)

    def test_cancelling_a_free_invoice(self) -> None:
        invoice = self.issue()
        page = self.assert_ok(self.client.get(f"/accounting/documents/{invoice.pk}/"))
        self.assertIn("Rechnung stornieren", page)
        response = self.client.post(f"/accounting/documents/{invoice.pk}/cancel/")
        cancellation = Document.objects.get(kind="cancellation")
        self.assertRedirects(response, f"/accounting/documents/{cancellation.pk}/")
        invoice.refresh_from_db()
        self.assertEqual(
            (cancellation.project, cancellation.customer, cancellation.cancels, invoice.cancelled_by, cancellation.number, cancellation.gross_total),
            (None, self.customer, invoice, cancellation, "RE-2027-0002", D("-476.00")),
        )  # fmt: skip
        text = stored_pdf(cancellation)
        self.assertIn("Stornorechnung", text)
        self.assertIn("RE-2027-0001", text)
        self.assertTrue(cancellation.xml_file)
        # Once only, and an offer is not cancelled.
        again = self.client.post(f"/accounting/documents/{invoice.pk}/cancel/", follow=True)
        self.assertEqual(Document.objects.filter(kind="cancellation").count(), 1)
        self.assertNotIn("Rechnung stornieren", self.assert_ok(self.client.get(f"/accounting/documents/{invoice.pk}/")))
        offer = self.issue(DocumentKind.OFFER)
        self.client.post(f"/accounting/documents/{offer.pk}/cancel/")
        self.assertEqual(Document.objects.filter(kind="cancellation").count(), 1)
        self.assertEqual(again.status_code, 200)

    def test_a_new_invoice_after_the_cancellation_is_free_to_make(self) -> None:
        """A document without a project is not tied to the one-open-invoice rule of a project."""
        first = self.issue()
        second = self.issue()
        self.assertEqual((first.number, second.number), ("RE-2027-0001", "RE-2027-0002"))

    def test_what_stops_an_invoice(self) -> None:
        from rentalars.core.models import CompanyProfile

        draft = self.make_draft()
        profile = CompanyProfile.load()
        profile.vat_id = ""
        profile.save()
        with self.assertRaises(ValidationError) as caught:
            free.issue(draft)
        self.assertIn("USt-IdNr.", " ".join(caught.exception.messages))
        self.assertFalse(Document.objects.exists())
        profile.vat_id = "DE999999999"
        profile.save()
        settings = SystemSettings.load()
        settings.invoices_enabled = False
        settings.save()
        with self.assertRaises(ValidationError):
            free.issue(draft)
        # Offers do not depend on invoices.
        self.assertEqual(self.issue(DocumentKind.OFFER).number, "AN-2027-0001")
        settings.invoices_enabled = True
        settings.save()
        self.assertEqual(free.issue(draft).number, "RE-2027-0001")  # no number was used up by the refusals

    def test_other_kinds_are_not_made_without_a_project(self) -> None:
        for kind in (DocumentKind.DELIVERY_NOTE, DocumentKind.CANCELLATION, DocumentKind.CREW_SHEET):
            with self.assertRaises(ValidationError):
                free.create_draft(self.customer, kind)
        self.assertEqual(set(FREE_KINDS), {"offer", "order_confirmation", "invoice"})


class FreeListTests(FreeCase):
    """Buchhaltung → Ausgangsbelege and the page of the customer show documents with and without a project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Sommerfest", customer=self.customer)
        add_line(self.project, self.cable, 2)
        self.of_project = services.create_document(self.project, DocumentKind.INVOICE)
        self.other = ready_for_invoices(make_customer("Theater am Markt"))
        self.free_invoice = self.issue(reference="Hochzeit Meier")
        draft = free.create_draft(self.other, DocumentKind.OFFER, reference="Messestand")
        free.add_line(draft, title="Stand", unit_price=D("100.00"))
        self.free_offer = free.issue(draft)

    def numbers(self, query: str = "") -> list[str]:
        return sorted(numbers_of(self.assert_ok(self.client.get(OUTGOING + query))))

    def test_both_in_the_list(self) -> None:
        page = self.assert_ok(self.client.get(OUTGOING))
        self.assertEqual(self.numbers(), ["AN-2027-0001", "RE-2027-0001", "RE-2027-0002"])
        self.assertIn("ohne Projekt", page)
        self.assertIn("Sommerfest", page)
        self.assertIn("Hochzeit Meier", page.replace("<div", " <div"))  # the reference stands under "ohne Projekt"
        link = f'href="/accounting/documents/{self.free_invoice.pk}/"'
        self.assertIn(link, page)

    def test_the_filter_by_origin(self) -> None:
        self.assertEqual(self.numbers("?origin=free"), ["AN-2027-0001", "RE-2027-0002"])
        self.assertEqual(self.numbers("?origin=project"), ["RE-2027-0001"])
        self.assertEqual(self.numbers("?origin="), ["AN-2027-0001", "RE-2027-0001", "RE-2027-0002"])
        page = self.assert_ok(self.client.get(OUTGOING))
        self.assertIn('name="origin"', page)
        self.assertIn("ohne Projekt</option>", page)
        # Combined with the other filters.
        self.assertEqual(self.numbers(f"?origin=free&customer={self.other.pk}"), ["AN-2027-0001"])
        self.assertEqual(self.numbers("?origin=free&kind=invoice"), ["RE-2027-0002"])

    def test_the_search_finds_the_reference_and_the_customer(self) -> None:
        self.assertEqual(self.numbers("?q=Hochzeit"), ["RE-2027-0002"])
        self.assertEqual(self.numbers("?q=Theater"), ["AN-2027-0001"])
        self.assertEqual(self.numbers("?q=Sommerfest"), ["RE-2027-0001"])

    def test_the_customer_filter_reaches_documents_without_a_project(self) -> None:
        self.assertEqual(self.numbers(f"?customer={self.customer.pk}"), ["RE-2027-0001", "RE-2027-0002"])
        page = self.assert_ok(self.client.get(OUTGOING))
        self.assertIn("Theater am Markt", page.split('id="f-customer"')[1].split("</select>")[0])

    def test_sums_columns_sorting_and_csv(self) -> None:
        page = self.assert_ok(self.client.get(OUTGOING))
        self.assertIn("476,00", page)  # the sums of the filtered documents include the free ones
        for query in ("?sort=customer", "?sort=-customer", "?sort=project", "?group=customer", "?group=project"):
            self.assert_ok(self.client.get(OUTGOING + query))
        csv_page = self.client.get(OUTGOING + "?format=csv&cols=all&origin=free")
        text = csv_page.content.decode("utf-8-sig")
        self.assertIn("RE-2027-0002", text)
        self.assertNotIn("RE-2027-0001", text)
        self.assertIn("ohne Projekt", text)
        self.assertIn("Hochzeit Meier", text)

    def test_the_drafts_stand_above_the_list(self) -> None:
        draft = self.make_draft(DocumentKind.OFFER, reference="Noch offen")
        page = self.assert_ok(self.client.get(OUTGOING))
        self.assertIn(f'href="/accounting/documents/drafts/{draft.pk}/"', page)
        self.assertIn("Noch offen", page)
        self.assertEqual(self.numbers(), ["AN-2027-0001", "RE-2027-0001", "RE-2027-0002"])  # a draft has no number

    def test_the_page_of_the_customer(self) -> None:
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk])))
        self.assertIn("Ausgangsbelege", page)
        self.assertIn("Rechnung RE-2027-0001", page)  # of the project
        self.assertIn("Rechnung RE-2027-0002", page)  # without one
        self.assertIn(f"/accounting/documents/{self.free_invoice.pk}/", page)
        self.assertIn("Neuer Ausgangsbeleg", page)
        self.assertIn(f"{NEW}?customer={self.customer.pk}", page)
        self.assertNotIn("AN-2027-0001", page)  # the document of the other customer
        # The dialog from this page starts with the customer.
        dialog = self.assert_ok(self.htmx("get", f"{NEW}?customer={self.customer.pk}"))
        self.assertIn(f'value="{self.customer.pk}"', dialog)
        self.assertIn("Bühnenwerk Köln", dialog)

    def test_the_page_of_a_customer_with_many_documents_leads_on(self) -> None:
        for _index in range(free.CUSTOMER_PAGE_LIMIT):
            self.issue(DocumentKind.ORDER_CONFIRMATION)
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk])))
        self.assertIn(f"{OUTGOING}?customer={self.customer.pk}", page)
        self.assertIn("Alle 12 Belege dieses Kunden", page)

    def test_a_free_document_is_in_no_project_figure(self) -> None:
        """The documents of a project stay as they were: the tab lists its own, the reminders look at projects."""
        tab = self.assert_ok(self.client.get(reverse("documents:list", args=[self.project.pk])))
        self.assertIn("RE-2027-0001", tab)
        self.assertNotIn("RE-2027-0002", tab)
        self.assertEqual(self.project.documents.count(), 1)
        from rentalars.projects.models import Project

        self.assertFalse(Project.objects.filter(documents__in=Document.objects.filter(project__isnull=True)).exists())

    def test_the_document_page_of_a_document_of_a_project_is_not_here(self) -> None:
        self.assertEqual(self.client.get(f"/accounting/documents/{self.of_project.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/accounting/documents/{self.of_project.pk}/cancel/").status_code, 404)
        self.assertEqual(self.client.get(f"/accounting/documents/{self.of_project.pk}/send/").status_code, 404)


class FreeRightsTests(FreeCase):
    """Who may look, who may make: the rights of the list (prices, every project) and of writing projects."""

    def setUp(self) -> None:
        super().setUp()
        self.draft = self.make_draft()
        self.document = self.issue()
        self.pages = {
            "new": NEW,
            "edit": f"/accounting/documents/drafts/{self.draft.pk}/",
            "document": f"/accounting/documents/{self.document.pk}/",
            "send": f"/accounting/documents/{self.document.pk}/send/",
        }

    def posts(self) -> list[str]:
        """The addresses that change something."""
        edit = self.pages["edit"]
        line = self.draft.lines.first().pk
        return [
            NEW,
            edit,
            f"{edit}lines/add/",
            f"{edit}lines/{line}/edit/",
            f"{edit}lines/{line}/delete/",
            f"{edit}lines/{line}/move/",
            f"{edit}issue/",
            f"{edit}delete/",
            self.pages["send"],
            f"/accounting/documents/{self.document.pk}/cancel/",
        ]

    def test_the_manager_makes_documents(self) -> None:
        manager = self.browser_for("paula", "Projektleitung")
        self.assertIn("Neuer Ausgangsbeleg", self.assert_ok(manager.get(OUTGOING)))
        for name, url in self.pages.items():
            self.assertEqual(manager.get(url).status_code, 200, name)

    def test_who_may_only_read_sees_but_does_not_make(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        page = self.assert_ok(reader.get(OUTGOING))
        self.assertNotIn("Neuer Ausgangsbeleg", page)
        self.assertIn("Entwürfe", page)
        self.assertEqual(reader.get(self.pages["new"]).status_code, 403)
        self.assertEqual(reader.get(self.pages["send"]).status_code, 403)
        # Looking: the draft and the document, without the buttons that change them.
        edit = self.assert_ok(reader.get(self.pages["edit"]))
        self.assertNotIn("Beleg ausstellen", edit)
        self.assertNotIn("Zeile hinzufügen", edit)
        document = self.assert_ok(reader.get(self.pages["document"]))
        self.assertNotIn("Rechnung stornieren", document)
        self.assertNotIn("Per E-Mail senden", document)
        for url in self.posts():
            self.assertEqual(reader.post(url).status_code, 403, url)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(DocumentDraft.objects.count(), 1)

    def test_without_the_price_right_nothing_is_open(self) -> None:
        storekeeper = self.browser_for("luka", "Lager")
        self.assertEqual(storekeeper.get(OUTGOING).status_code, 403)
        for url in self.pages.values():
            self.assertEqual(storekeeper.get(url).status_code, 403, url)
        for url in self.posts():
            self.assertEqual(storekeeper.post(url).status_code, 403, url)

    def test_who_reads_only_assigned_projects_has_no_access(self) -> None:
        assigned = role("Disposition eigene", {"projects": 2, "customers": 1}, ["prices"], ProjectScope.ASSIGNED)
        browser = self.browser_of(_user_with("ida", assigned))
        for url in [*self.pages.values(), OUTGOING]:
            self.assertEqual(browser.get(url).status_code, 403, url)

    def test_write_access_to_every_project_is_needed_to_change(self) -> None:
        """Reading every project and seeing prices lets one look; making needs write access to projects."""
        looker = role("Nur Preise lesen", {"projects": 1, "customers": 1}, ["prices"])
        browser = self.browser_of(_user_with("olga", looker))
        self.assertEqual(browser.get(self.pages["edit"]).status_code, 200)
        self.assertEqual(browser.post(f"{self.pages['edit']}issue/").status_code, 403)

    def test_the_document_file_follows_the_same_rights(self) -> None:
        file_url = reverse("documents:file", args=[self.document.pk])
        self.assertEqual(self.client.get(file_url).status_code, 200)
        self.assertEqual(self.browser_for("luka", "Lager").get(file_url).status_code, 403)
        self.assertEqual(self.browser_for("rita", "Nur-Lesen").get(file_url).status_code, 200)
        self.assertEqual(
            self.browser_for("rita2", "Nur-Lesen").get(reverse("documents:xml", args=[self.document.pk])).status_code,
            200,
        )

    def test_the_cancellation_by_a_reader_is_refused(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        self.assertEqual(reader.post(reverse("documents:cancel", args=[self.document.pk])).status_code, 403)
        self.assertFalse(Document.objects.filter(kind="cancellation").exists())


def _user_with(username: str, assigned: Any) -> Any:
    """A user with one role."""
    from tests.helpers import make_user

    user = make_user(username)
    user.roles.set([assigned])
    return user


class FreeCustomerStateTests(FreeCase):
    """Anonymised and deactivated customers get no new documents (KND-010)."""

    def test_a_deactivated_customer_is_not_offered_and_refused(self) -> None:
        self.customer.is_active = False
        self.customer.save()
        response = self.htmx("post", NEW, {"kind": "offer", "customer": self.customer.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DocumentDraft.objects.exists())
        with self.assertRaises(ValidationError) as caught:
            free.create_draft(self.customer, DocumentKind.OFFER)
        self.assertIn("deaktiviert", " ".join(caught.exception.messages))
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk])))
        self.assertNotIn(f"{NEW}?customer={self.customer.pk}", page)

    def test_an_anonymised_customer_is_refused(self) -> None:
        document = self.issue()
        customer_services.anonymise_customer(self.customer)
        self.customer.refresh_from_db()
        response = self.htmx("post", NEW, {"kind": "offer", "customer": self.customer.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DocumentDraft.objects.exists())
        with self.assertRaises(ValidationError) as caught:
            free.create_draft(self.customer, DocumentKind.OFFER)
        self.assertIn("anonymisiert", " ".join(caught.exception.messages))
        # What was issued before stays, as the documents of projects do.
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())
        self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk])))

    def test_anonymising_throws_the_drafts_away(self) -> None:
        self.make_draft()
        self.make_draft(DocumentKind.OFFER)
        other = DocumentDraft.objects.count()
        stranger = free.create_draft(make_customer("Anderer"), DocumentKind.OFFER)
        customer_services.anonymise_customer(self.customer)
        self.assertEqual((other, list(DocumentDraft.objects.all())), (2, [stranger]))
        self.assertFalse(DraftLine.objects.exists())

    def test_a_draft_of_a_customer_who_was_deactivated_cannot_be_issued(self) -> None:
        draft = self.make_draft()
        self.customer.is_active = False
        self.customer.save()
        page = self.assert_ok(self.client.get(f"/accounting/documents/drafts/{draft.pk}/"))
        self.assertIn("deaktiviert", page)
        with self.assertRaises(ValidationError):
            free.issue(draft)
        self.assertFalse(Document.objects.exists())
        self.customer.is_active = True
        self.customer.save()
        self.assertEqual(free.issue(draft).number, "RE-2027-0001")

    def test_a_customer_with_documents_cannot_be_deleted(self) -> None:
        from django.db.models import ProtectedError

        self.issue()
        with self.assertRaises(ProtectedError):
            self.customer.delete()


class FreeApiTests(FreeData, ApiTestCase):
    """``/accounting/documents/drafts`` and what belongs to it (API-014: every operation, success and refusal)."""

    def setUp(self) -> None:
        super().setUp()
        self.build()
        self.drafts = f"{API}/accounting/documents/drafts"

    def create(self, **fields: Any) -> dict[str, Any]:
        body = {"kind": "invoice", "customer": self.customer.pk, "reference": "Sommerfest 2027", **fields}
        response = self.admin.post(self.drafts, body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_create_a_draft_with_its_lines(self) -> None:
        draft = self.create(
            lines=[
                {"title": "Aufbau", "quantity": "2", "unit_price": "50.00"},
                {"product": self.pa.pk, "quantity": "3"},
                {"title": "Danke", "is_text": True},
            ]
        )
        self.assertEqual(
            (
                draft["kind"],
                draft["customer"],
                draft["reference"],
                draft["print_product_descriptions"],
                draft["problems"],
            ),
            ("invoice", self.customer.pk, "Sommerfest 2027", False, []),
        )
        self.assertEqual(
            [(line["title"], line["quantity"], line["unit_price"], line["amount"], line["is_text"]) for line in draft["lines"]],
            [("Aufbau", "2.00", "50.00", "100.00", False), ("PA-Anlage", "3.00", "100.00", "300.00", False), ("Danke", "1.00", "0.00", None, True)],
        )  # fmt: skip
        self.assertEqual((draft["net_total"], draft["tax_total"], draft["gross_total"]), ("400.00", "76.00", "476.00"))
        self.assertEqual([line["position"] for line in draft["lines"]], [1, 2, 3])
        self.assertIn("Wir berechnen", draft["introduction"])

    def test_create_with_the_choice_of_the_descriptions(self) -> None:
        printed = self.create(print_product_descriptions=True, lines=[{"product": self.pa.pk}])
        self.assertTrue(printed["print_product_descriptions"])
        self.assertFalse(self.create(lines=[])["print_product_descriptions"])
        self.assertFalse(self.create(print_product_descriptions=None)["print_product_descriptions"])
        issued = self.admin.post(f"{self.drafts}/{printed['id']}/issue", format="json")
        self.assertIn(DESCRIPTION, stored_pdf(Document.objects.get(pk=issued.json()["id"])))

    def test_create_is_refused_for_what_does_not_fit(self) -> None:
        for body, field in (
            ({"kind": "delivery_note", "customer": self.customer.pk}, "kind"),
            ({"kind": "invoice"}, "customer"),
            ({"kind": "invoice", "customer": 99999}, "customer"),
            ({"kind": "offer", "customer": self.customer.pk, "payment_terms_days": 10}, "kind"),
            ({"kind": "invoice", "customer": self.customer.pk, "contact": 99999}, "contact"),
            (
                {"kind": "invoice", "customer": self.customer.pk, "lines": [{"title": "", "unit_price": "1.00"}]},
                "title",
            ),
            (
                {"kind": "invoice", "customer": self.customer.pk, "lines": [{"title": "X", "unit_price": "-1.00"}]},
                "lines.0.unit_price",
            ),
        ):
            with self.subTest(body=body):
                self.assert_error(self.admin.post(self.drafts, body, format="json"), 400, "validation_error", field)
        self.assertFalse(DocumentDraft.objects.exists())  # a refused line leaves no half-made draft
        self.customer.is_active = False
        self.customer.save()
        self.assert_error(self.admin.post(self.drafts, {"kind": "offer", "customer": self.customer.pk}, format="json"), 400, "validation_error", "customer")  # fmt: skip

    def test_an_anonymised_customer_is_refused(self) -> None:
        customer_services.anonymise_customer(self.customer)
        self.assert_error(self.admin.post(self.drafts, {"kind": "offer", "customer": self.customer.pk}, format="json"), 400, "validation_error", "customer")  # fmt: skip

    def test_list_and_read(self) -> None:
        first = self.create()
        second = self.create(kind="offer", reference="Messe")
        listed = self.admin.get(self.drafts).json()
        self.assertEqual(listed["count"], 2)  # paged like every list (API-007)
        self.assertEqual([entry["id"] for entry in listed["results"]], [second["id"], first["id"]])
        one = self.admin.get(f"{self.drafts}/{first['id']}").json()
        self.assertEqual((one["id"], one["kind"], one["lines"]), (first["id"], "invoice", []))
        self.assertEqual(one["problems"], ["Füge mindestens eine Zeile mit Preis hinzu."])
        self.assert_error(self.admin.get(f"{self.drafts}/99999"), 404, "not_found")

    def test_change_the_header_and_the_texts(self) -> None:
        draft = self.create(lines=[{"product": self.pa.pk}])
        url = f"{self.drafts}/{draft['id']}"
        changed = self.admin.patch(
            url,
            {"reference": "Neu", "introduction": "Hallo", "closing": "Tschüss", "payment_terms_days": 7,
             "print_product_descriptions": True, "issued_on": "2027-02-20", "text_blocks": []},
            format="json",
        )  # fmt: skip
        self.assertEqual(changed.status_code, 200, changed.content)
        body = changed.json()
        self.assertEqual((body["reference"], body["introduction"], body["closing"], body["payment_terms_days"], body["print_product_descriptions"], body["issued_on"]), ("Neu", "Hallo", "Tschüss", 7, True, "2027-02-20"))  # fmt: skip
        # Nothing else changes; kind and customer stay.
        again = self.admin.patch(url, {"kind": "offer", "customer": 99999, "reference": "Zwei"}, format="json").json()
        self.assertEqual((again["kind"], again["customer"], again["reference"], again["introduction"]), ("invoice", self.customer.pk, "Zwei", "Hallo"))  # fmt: skip
        self.assert_error(
            self.admin.patch(url, {"valid_until": "2027-04-01"}, format="json"), 400, "validation_error", "valid_until"
        )
        self.assert_error(
            self.admin.patch(url, {"payment_terms_days": 400}, format="json"),
            400,
            "validation_error",
            "payment_terms_days",
        )
        self.assert_error(self.admin.patch(f"{self.drafts}/99999", {}, format="json"), 404, "not_found")

    def test_the_lines(self) -> None:
        draft = self.create()
        lines = f"{self.drafts}/{draft['id']}/lines"
        free_line = self.admin.post(
            lines, {"title": "Aufbau", "quantity": "2", "unit_price": "50.00", "discount_percent": "10"}, format="json"
        )
        self.assertEqual(free_line.status_code, 201, free_line.content)
        self.assertEqual((free_line.json()["amount"], free_line.json()["tax_rate"]), ("90.00", self.rate.pk))
        from_product = self.admin.post(
            lines, {"product": self.cable.pk, "quantity": "4", "tax_rate": self.seven.pk}, format="json"
        ).json()
        self.assertEqual((from_product["title"], from_product["unit_price"], from_product["amount"], from_product["tax_rate"]), ("Kabel", "5.00", "20.00", self.seven.pk))  # fmt: skip
        text = self.admin.post(lines, {"title": "Hinweis", "note": "bar", "is_text": True}, format="json").json()
        self.assertEqual((text["is_text"], text["amount"], text["note"]), (True, None, "bar"))
        # Change one line.
        line_url = f"{lines}/{free_line.json()['id']}"
        changed = self.admin.patch(
            line_url, {"title": "Aufbau groß", "unit_price": "60.00", "discount_percent": "0"}, format="json"
        )
        self.assertEqual((changed.json()["title"], changed.json()["amount"]), ("Aufbau groß", "120.00"))
        self.assert_error(
            self.admin.patch(line_url, {"quantity": "-1"}, format="json"), 400, "validation_error", "quantity"
        )
        self.assert_error(self.admin.patch(f"{lines}/99999", {}, format="json"), 404, "not_found")
        # Totals follow: 120,00 at 19 % and 20,00 at 7 %.
        detail = self.admin.get(f"{self.drafts}/{draft['id']}").json()
        self.assertEqual(
            (detail["net_total"], detail["tax_total"], detail["gross_total"]), ("140.00", "24.20", "164.20")
        )
        # The order.
        ids = [line["id"] for line in detail["lines"]]
        ordered = self.admin.post(f"{lines}/order", {"lines": [ids[2], ids[0]]}, format="json")
        self.assertEqual([line["id"] for line in ordered.json()["lines"]], [ids[2], ids[0], ids[1]])
        self.assertEqual([line["position"] for line in ordered.json()["lines"]], [1, 2, 3])
        self.assert_error(
            self.admin.post(f"{lines}/order", {"lines": [99999]}, format="json"), 400, "validation_error", "lines"
        )
        self.assert_error(self.admin.post(f"{lines}/order", {}, format="json"), 400, "validation_error", "lines")
        # Remove one.
        self.assertEqual(self.admin.delete(line_url).status_code, 204)
        self.assertEqual(self.admin.delete(line_url).status_code, 404)
        self.assertEqual(len(self.admin.get(f"{self.drafts}/{draft['id']}").json()["lines"]), 2)

    def test_what_cannot_be_a_line(self) -> None:
        draft = self.create()
        lines = f"{self.drafts}/{draft['id']}/lines"
        vehicle = make_product(
            "V-100", "Transporter", price=None, kind="vehicle", vehicle_type="car", price_per_km=D("0.80")
        )
        self.assert_error(
            self.admin.post(lines, {"product": vehicle.pk}, format="json"), 400, "validation_error", "product"
        )
        self.assert_error(self.admin.post(lines, {"product": 99999}, format="json"), 400, "validation_error", "product")
        self.assert_error(
            self.admin.post(lines, {"unit_price": "1.00"}, format="json"), 400, "validation_error", "title"
        )
        self.assert_error(
            self.admin.post(f"{self.drafts}/99999/lines", {"title": "X"}, format="json"), 404, "not_found"
        )

    def test_the_draft_pdf(self) -> None:
        draft = self.create(lines=[{"product": self.pa.pk}], print_product_descriptions=True)
        response = self.admin.post(f"{self.drafts}/{draft['id']}/preview", format="json")
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(DESCRIPTION, pdf_words(response.content))
        self.assertFalse(Document.objects.exists())
        empty = self.create()
        self.assert_error(
            self.admin.post(f"{self.drafts}/{empty['id']}/preview", format="json"), 400, "validation_error"
        )
        self.assert_error(self.admin.post(f"{self.drafts}/99999/preview", format="json"), 404, "not_found")

    def test_issue_and_what_follows(self) -> None:
        draft = self.create(
            lines=[
                {"title": "Aufbau", "quantity": "2", "unit_price": "50.00"},
                {"product": self.pa.pk, "quantity": "3"},
            ]
        )
        issued = self.admin.post(f"{self.drafts}/{draft['id']}/issue", format="json")
        self.assertEqual(issued.status_code, 201, issued.content)
        document = issued.json()
        self.assertEqual(
            (document["project"], document["customer"], document["kind"], document["number"], document["gross_total"], document["reference"]),
            (None, self.customer.pk, "invoice", "RE-2027-0001", "476.00", "Sommerfest 2027"),
        )  # fmt: skip
        self.assertFalse(DocumentDraft.objects.exists())
        self.assert_error(self.admin.get(f"{self.drafts}/{draft['id']}"), 404, "not_found")
        self.assert_error(self.admin.post(f"{self.drafts}/{draft['id']}/issue", format="json"), 404, "not_found")
        # The document is one like the others: read, PDF, XRechnung, list, cancellation.
        self.assertEqual(self.admin.get(f"{API}/documents/{document['id']}").json()["project"], None)
        self.assertEqual(self.admin.get(document["pdf_url"]).status_code, 200)
        self.assertEqual(self.admin.get(document["xml_url"]).status_code, 200)
        listed = self.admin.get(f"{API}/accounting/documents", {"origin": "free"}).json()
        self.assertEqual([(row["number"], row["project"], row["project_number"], row["reference"], row["customer"]) for row in listed["results"]], [("RE-2027-0001", None, "", "Sommerfest 2027", self.customer.pk)])  # fmt: skip
        project = make_project("Sommerfest", customer=self.customer)
        add_line(project, self.cable, 1)
        services.create_document(project, DocumentKind.OFFER)
        everything = self.admin.get(f"{API}/accounting/documents").json()
        self.assertEqual(sorted(row["number"] for row in everything["results"]), ["AN-2027-0001", "RE-2027-0001"])
        self.assertEqual([row["number"] for row in self.admin.get(f"{API}/accounting/documents", {"origin": "project"}).json()["results"]], ["AN-2027-0001"])  # fmt: skip
        self.assertEqual(self.admin.get(f"{API}/accounting/documents/totals", {"origin": "free"}).json()["kinds"][0]["gross_total"], "476.00")  # fmt: skip
        cancellation = self.admin.post(f"{API}/documents/{document['id']}/cancel", format="json")
        self.assertEqual(cancellation.status_code, 201, cancellation.content)
        self.assertEqual((cancellation.json()["project"], cancellation.json()["number"], cancellation.json()["gross_total"]), (None, "RE-2027-0002", "-476.00"))  # fmt: skip

    def test_issue_is_refused_when_something_stops_it(self) -> None:
        empty = self.create()
        self.assert_error(self.admin.post(f"{self.drafts}/{empty['id']}/issue", format="json"), 400, "validation_error")
        settings = SystemSettings.load()
        settings.invoices_enabled = False
        settings.save()
        full = DocumentDraft.objects.get(pk=empty["id"])
        free.add_line(full, title="X", unit_price=D("1.00"))
        self.assert_error(self.admin.post(f"{self.drafts}/{empty['id']}/issue", format="json"), 400, "validation_error")
        self.assert_error(self.admin.post(self.drafts, {"kind": "invoice", "customer": self.customer.pk}, format="json"), 400, "validation_error", "kind")  # fmt: skip
        self.assertFalse(Document.objects.exists())

    def test_delete_a_draft(self) -> None:
        draft = self.create(lines=[{"title": "X", "unit_price": "1.00"}])
        self.assertEqual(self.admin.delete(f"{self.drafts}/{draft['id']}").status_code, 204)
        self.assertFalse(DocumentDraft.objects.exists() or DraftLine.objects.exists())
        self.assert_error(self.admin.delete(f"{self.drafts}/{draft['id']}"), 404, "not_found")
        issued = self.admin.post(
            f"{self.drafts}/{self.create(lines=[{'title': 'Y', 'unit_price': '2.00'}])['id']}/issue", format="json"
        )
        self.assertEqual(issued.json()["number"], "RE-2027-0001")

    def test_send_by_mail(self) -> None:
        configure_mailbox()
        document = self.issue()
        url = f"{API}/accounting/documents/{document.pk}/send"
        with capture_smtp() as sent:
            response = self.admin.post(url, {"to": "kasse@buehnenwerk.example", "xml": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["sent_to"], "kasse@buehnenwerk.example")
        (message,) = sent
        self.assertEqual([part.get_filename() for part in message.iter_attachments()], ["Rechnung-RE-2027-0001.pdf", "RE-2027-0001.xml"])  # fmt: skip
        self.assertIn("Anbei erhalten Sie unsere Rechnung", message.get_body().get_content())
        with capture_smtp() as sent:
            self.assert_error(self.admin.post(url, {"to": "kein-mail"}, format="json"), 400, "validation_error", "to")
            self.assert_error(self.admin.post(url, {}, format="json"), 400, "validation_error", "to")
        self.assertEqual(sent, [])
        self.assert_error(self.admin.post(f"{API}/accounting/documents/99999/send", {"to": "a@b.example"}, format="json"), 404, "not_found")  # fmt: skip
        # A document of a project is sent from the correspondence of the project.
        project = make_project("Sommerfest", customer=self.customer)
        add_line(project, self.cable, 1)
        of_project = services.create_document(project, DocumentKind.OFFER)
        self.assert_error(self.admin.post(f"{API}/accounting/documents/{of_project.pk}/send", {"to": "a@b.example"}, format="json"), 404, "not_found")  # fmt: skip

    def test_without_a_mailbox_sending_is_refused(self) -> None:
        document = self.issue()
        response = self.admin.post(
            f"{API}/accounting/documents/{document.pk}/send", {"to": "a@b.example"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_the_rights(self) -> None:
        draft = self.create(lines=[{"title": "X", "unit_price": "1.00"}])
        document = self.issue()
        reader = self.client_for("rita", "Nur-Lesen")
        storekeeper = self.client_for("luka", "Lager")
        manager = self.client_for("paula", "Projektleitung")
        url = f"{self.drafts}/{draft['id']}"
        reads = [self.drafts, url, f"{API}/documents/{document.pk}", f"{API}/documents/{document.pk}/pdf"]
        changes = [
            ("post", self.drafts, {"kind": "offer", "customer": self.customer.pk}),
            ("patch", url, {"reference": "x"}),
            ("delete", url, None),
            ("post", f"{url}/lines", {"title": "Y"}),
            ("post", f"{url}/lines/order", {"lines": []}),
            ("post", f"{url}/issue", None),
            ("post", f"{API}/documents/{document.pk}/cancel", None),
            ("post", f"{API}/accounting/documents/{document.pk}/send", {"to": "a@b.example"}),
        ]
        for read in reads:
            self.assertEqual(reader.get(read).status_code, 200, read)
            self.assertEqual(storekeeper.get(read).status_code, 403, read)
            self.assertEqual(manager.get(read).status_code, 200, read)
        for method, address, body in changes:
            with self.subTest(method=method, address=address):
                self.assertEqual(getattr(reader, method)(address, body, format="json").status_code, 403)
                self.assertEqual(getattr(storekeeper, method)(address, body, format="json").status_code, 403)
        # A preview is a POST: whoever may not write drafts may not ask for one.
        self.assertEqual(reader.post(f"{url}/preview", format="json").status_code, 403)
        self.assertEqual(storekeeper.post(f"{url}/preview", format="json").status_code, 403)
        self.assertEqual(manager.post(self.drafts, {"kind": "offer", "customer": self.customer.pk}, format="json").status_code, 201)  # fmt: skip
        self.assertEqual(DocumentDraft.objects.count(), 2)
        self.assertEqual(Document.objects.filter(kind="cancellation").count(), 0)

    def test_the_document_serializer_has_the_new_fields(self) -> None:
        document = self.issue(reference="Hochzeit")
        body = self.admin.get(f"{API}/documents/{document.pk}").json()
        self.assertEqual((body["project"], body["customer"], body["reference"], body["print_product_descriptions"]), (None, self.customer.pk, "Hochzeit", False))  # fmt: skip
        project = make_project("Sommerfest", customer=self.customer)
        add_line(project, self.cable, 1)
        of_project = services.create_document(project, DocumentKind.OFFER)
        body = self.admin.get(f"{API}/documents/{of_project.pk}").json()
        self.assertEqual((body["project"], body["customer"], body["reference"]), (project.pk, self.customer.pk, ""))
        self.assertEqual(len(self.admin.get(f"{API}/projects/{project.pk}/documents").json()), 1)


class FreeIntegrationTests(FreeCase):
    """Where else a document looks at its project: the webhook, the history, the log of what was looked at."""

    def test_the_webhook_event_has_no_project(self) -> None:
        from rentalars.api.models import WebhookDelivery
        from tests.unit.test_060_webhooks import make_hook

        make_hook("document.created")
        free_invoice = self.issue()
        project = make_project("Sommerfest", customer=self.customer)
        add_line(project, self.cable, 1)
        services.create_document(project, DocumentKind.OFFER)
        free_event, project_event = (delivery.data for delivery in WebhookDelivery.objects.order_by("pk"))
        self.assertEqual((free_event["project"], free_event["document"]["id"]), (None, free_invoice.pk))
        self.assertEqual(project_event["project"]["id"], project.pk)

    def test_the_history_of_the_customer_tells_what_happened(self) -> None:
        invoice = self.issue()
        services.mark_sent(invoice, "kasse@example.de")
        services.cancel_invoice(invoice)
        self.make_draft(DocumentKind.OFFER)
        free.delete_draft(DocumentDraft.objects.get())
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.customer.pk])))
        history = page.split("Verlauf")[-1]
        for expected in (
            "Rechnung RE-2027-0001 erstellt",
            "Rechnung RE-2027-0001 an kasse@example.de gesendet",
            "Rechnung RE-2027-0001 storniert durch RE-2027-0002",
            "Entwurf (Angebot) ohne Projekt gelöscht",
        ):
            self.assertIn(expected, " ".join(history.split()))

    def test_the_log_of_what_was_looked_at_names_the_customer(self) -> None:
        from rentalars.core import access_log

        document = self.issue()
        target = access_log._document(document.pk, self.admin_user, None)
        self.assertEqual(
            (target.parent_kind, target.parent_id), (access_log.AccessKind.CUSTOMER, str(self.customer.pk))
        )
        self.assertIn("RE-2027-0001", target.label)
        self.assertEqual(self.client.get(reverse("documents:file", args=[document.pk])).status_code, 200)

    def test_a_draft_and_its_lines_are_in_the_change_log_of_the_customer(self) -> None:
        from rentalars.core.models import AuditLogEntry

        draft = self.make_draft()
        draft.reference = "Neu"
        draft.save()
        entries = AuditLogEntry.objects.filter(
            parent_content_type__model="customer", parent_object_id=str(self.customer.pk)
        )
        self.assertEqual(
            sorted({(entry.content_type.model, entry.action) for entry in entries}),
            [("documentdraft", "created"), ("documentdraft", "updated"), ("draftline", "created")],
        )
        update = entries.get(content_type__model="documentdraft", action="updated")
        self.assertEqual(update.changes["reference"], ["", "Neu"])
        self.assertNotIn("changed_at", update.changes)
        self.assertIn(entries.first(), list(AuditLogEntry.for_object(self.customer)))


class TemplateSettingTests(FreeCase):
    """The default of the description choice and the introduction without a project stand in the template (DOK-005)."""

    def change_page(self, kind: str) -> str:
        template = services.template_for(kind)
        return self.assert_ok(self.client.get(reverse("admin:documents_documenttemplate_change", args=[template.pk])))

    def test_the_fields_stand_where_they_belong(self) -> None:
        offer = self.change_page("offer")
        self.assertIn('name="print_product_descriptions"', offer)
        self.assertIn('name="free_introduction"', offer)
        invoice = self.change_page("invoice")
        self.assertIn('name="print_product_descriptions"', invoice)
        self.assertIn('name="free_introduction"', invoice)
        for kind in ("crew_sheet", "cancellation"):
            page = self.change_page(kind)
            self.assertNotIn('name="print_product_descriptions"', page, kind)
        for kind in ("delivery_note", "crew_sheet", "cancellation"):
            self.assertNotIn('name="free_introduction"', self.change_page(kind), kind)
        self.assertIn('name="print_product_descriptions"', self.change_page("delivery_note"))

    def test_saving_the_default(self) -> None:
        template = services.template_for("invoice")
        page = self.client.get(reverse("admin:documents_documenttemplate_change", args=[template.pk]))
        data = form_data(page, containing="free_introduction", print_product_descriptions="on")
        saved = self.client.post(reverse("admin:documents_documenttemplate_change", args=[template.pk]), data)
        self.assertEqual(saved.status_code, 302, saved.content.decode()[:300])
        template.refresh_from_db()
        self.assertTrue(template.print_product_descriptions)
        self.assertTrue(self.make_draft().print_product_descriptions)  # a new free document starts with it
        self.assertFalse(self.make_draft(DocumentKind.OFFER).print_product_descriptions)

    def test_the_introduction_of_a_free_document_comes_from_the_template(self) -> None:
        self.assertIn("Wir berechnen Ihnen:", free.default_introduction("invoice"))
        template = services.template_for("invoice")
        template.free_introduction = "Für {customer} stellen wir in Rechnung:"
        template.save()
        document = self.issue()
        self.assertIn("Für Bühnenwerk Köln stellen wir in Rechnung:", stored_pdf(document))


# --- Review findings (free documents; DOK-022) ------------------------------------------------------------


class ReviewPlaceholderTests(FreeCase):
    """A text with a placeholder that cannot be filled never stops a page, the preview or the issuing."""

    TEXTS = "Hallo {customer.name}, {0} {kunde} {customer[0]} {{keep}} {valid_until:%Y} {broken"

    def test_fill_leaves_what_it_cannot_fill_as_written(self) -> None:
        values = {"customer": "Bühnenwerk", "project": "", "due_date": "01.04.2027"}
        cases = {
            "{customer.name}": "{customer.name}",
            "{customer[0]}": "{customer[0]}",
            "{0}": "{0}",
            "{}": "{}",
            "{kunde}": "{kunde}",
            "{customer!r}": "'Bühnenwerk'",
            "{customer} und {customer.name}": "Bühnenwerk und {customer.name}",
            "{{customer}}": "{customer}",
            "{customer:>12}": "  Bühnenwerk",
            "{customer:%Y}": "{customer:%Y}",
            "{customer:{project}}": "{customer:{project}}",
            "{customer} {": "{customer} {",
            "": "",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(builder.fill(text, values), expected)

    def test_the_unknown_ones_are_named(self) -> None:
        values = {"customer": "x", "due_date": ""}
        self.assertEqual(
            builder.unknown_placeholders("{customer} {customer.name} {x} {x} {0}", values),
            ["{customer.name}", "{x}", "{0}"],
        )
        self.assertEqual(builder.unknown_placeholders("Text {customer", values), ["{customer"])
        self.assertEqual(builder.unknown_placeholders("", values), [])

    def test_the_texts_of_projects_are_tolerant_too(self) -> None:
        project = make_project("Sommerfest", customer=self.customer)
        values = builder.placeholder_values(project)
        self.assertEqual(builder.fill("{customer.name} / {customer}", values), "{customer.name} / Bühnenwerk Köln")

    def test_the_page_the_preview_and_the_issuing_print_it_as_written(self) -> None:
        draft = self.make_draft(DocumentKind.OFFER, introduction=self.TEXTS, closing="Ihr {customer.name}")
        edit = f"/accounting/documents/drafts/{draft.pk}/"
        page = self.assert_ok(self.client.get(edit))
        self.assertIn("data-draft-hints", page)
        for unknown in ("{customer.name}", "{0}", "{kunde}", "{customer[0]}"):
            self.assertIn(html.escape(unknown, quote=False), page)
        preview = self.client.post(f"{edit}preview/")
        self.assertEqual(preview.status_code, 200)
        self.assertIn("{customer.name}", pdf_text(preview))
        issued = self.client.post(f"{edit}issue/")
        self.assertEqual(issued.status_code, 302, issued.content.decode()[:300])
        text = stored_pdf(Document.objects.get())
        self.assertIn("Hallo {customer.name}", text)
        self.assertIn("{kunde}", text)
        self.assertIn("{keep}", text)
        self.assertIn("Ihr {customer.name}", text)

    def test_the_hint_is_not_shown_without_unknown_placeholders(self) -> None:
        draft = self.make_draft(DocumentKind.OFFER, introduction="Für {customer}")
        self.assertNotIn(
            "data-draft-hints", self.assert_ok(self.client.get(f"/accounting/documents/drafts/{draft.pk}/"))
        )
        self.assertEqual(free.placeholder_hints(draft), [])

    def test_the_service_previews_and_issues_it_too(self) -> None:
        draft = self.make_draft(DocumentKind.OFFER, introduction="Hallo {customer.name}")
        free.preview(draft)
        self.assertIn("Hallo {customer.name}", stored_pdf(free.issue(draft)))


class ReviewGreetingTests(FreeCase):
    """``{greeting}`` and ``{anrede}`` in the texts of a free document (KND-004)."""

    def pdf_of(self, **fields: Any) -> str:
        return stored_pdf(self.issue(DocumentKind.OFFER, **{"introduction": "{greeting} / {anrede}", **fields}))

    def test_the_greeting_of_the_contact_of_the_draft(self) -> None:
        from rentalars.customers.models import Contact

        contact = Contact.objects.create(customer=self.customer, salutation="Frau", first_name="Anna", last_name="Berg")
        text = self.pdf_of(contact=contact)
        self.assertIn("Sehr geehrte Frau Berg, / Sehr geehrte Frau Berg,", text)
        self.assertNotIn("{greeting}", text)

    def test_the_personal_greeting_follows_the_contact(self) -> None:
        from rentalars.customers.models import Contact

        contact = Contact.objects.create(
            customer=self.customer, first_name="Anna", last_name="Berg", greeting_style="personal"
        )
        self.assertIn("Hallo Anna, / Hallo Anna,", self.pdf_of(contact=contact))

    def test_without_a_contact_of_the_draft_the_main_contact_speaks(self) -> None:
        from rentalars.customers.models import Contact

        Contact.objects.create(customer=self.customer, salutation="Herr", last_name="Moor", is_primary=True)
        draft = self.make_draft(DocumentKind.OFFER, introduction="{greeting}")
        DocumentDraft.objects.filter(pk=draft.pk).update(contact=None)
        self.assertIn("Sehr geehrter Herr Moor,", stored_pdf(free.issue(DocumentDraft.objects.get(pk=draft.pk))))

    def test_without_any_contact_the_neutral_formal_greeting(self) -> None:
        from rentalars.customers import greetings

        neutral = greetings.neutral_greeting("de")
        self.assertTrue(neutral)
        # "Sehr geehrte Damen und Herren," once the German texts are compiled; the English msgid until then.
        self.assertIn(neutral, ("Sehr geehrte Damen und Herren,", "Dear Sir or Madam,"))
        self.assertEqual(greetings.neutral_greeting("en"), "Dear Sir or Madam,")
        text = self.pdf_of()
        self.assertIn(f"{neutral} / {neutral}", text)
        self.assertNotIn("{greeting}", text)
        self.assertNotIn("{anrede}", text)

    def test_the_placeholders_are_known_to_the_hint(self) -> None:
        draft = self.make_draft(DocumentKind.OFFER, introduction="{greeting}{anrede}")
        self.assertEqual(free.placeholder_hints(draft), [])


class ReviewDraftPageTests(FreeCase):
    """The page of a draft stays open and editable whatever the draft holds."""

    def test_an_offer_whose_validity_has_passed_still_opens_and_can_be_corrected(self) -> None:
        draft = self.make_draft(DocumentKind.OFFER, valid_until=datetime.date(2027, 3, 10))
        # Time passes: the date of the offer is the day it is issued, now after the validity.
        DocumentDraft.objects.filter(pk=draft.pk).update(valid_until=datetime.date(2027, 2, 20))
        edit = f"/accounting/documents/drafts/{draft.pk}/"
        response = self.client.get(edit)
        page = self.assert_ok(response)
        self.assertTrue(response.context["problems"], "the page names what is wrong")
        self.assertIn("data-draft-problems", page)
        self.assertIn("disabled", page.split("Beleg ausstellen")[0].rsplit("<button", 1)[1])
        # It can be corrected on the page itself.
        data = form_data(response, containing="introduction")
        data["valid_until"] = "2027-03-31"
        saved = self.client.post(edit, data)
        self.assertEqual(saved.status_code, 302, saved.content.decode()[:300])
        self.assertEqual(self.client.get(edit).context["problems"], [])
        # Nor do the preview and the issuing of a draft that is wrong answer with an error of the server.
        DocumentDraft.objects.filter(pk=draft.pk).update(valid_until=datetime.date(2027, 2, 20))
        for action in ("preview", "issue"):
            answer = self.client.post(f"{edit}{action}/")
            self.assertEqual(answer.status_code, 302, action)
        self.assertFalse(Document.objects.exists())

    def test_page_content_names_what_stops_it(self) -> None:
        draft = self.make_draft(DocumentKind.OFFER, valid_until=datetime.date(2027, 3, 10))
        DocumentDraft.objects.filter(pk=draft.pk).update(valid_until=datetime.date(2027, 2, 20))
        draft.refresh_from_db()
        content, messages = free.page_content(draft, free.calculate(free.lines_of(draft)))
        self.assertIsNone(content)
        self.assertTrue(messages)


class ReviewIssueTwiceTests(FreeCase):
    """Two people issue the same draft: the second one is told, not served a server error."""

    def test_the_second_issue_is_a_validation_error(self) -> None:
        stale = DocumentDraft.objects.get(pk=self.make_draft().pk)
        free.issue(stale)
        with self.assertRaises(ValidationError) as caught:
            free.issue(stale)
        self.assertEqual(caught.exception.code, "already_issued")
        self.assertEqual(Document.objects.count(), 1)

    def test_the_page_answers_with_a_message(self) -> None:
        draft = DocumentDraft.objects.get(pk=self.make_draft().pk)
        free.issue(draft)
        with mock.patch("rentalars.documents.free_views._draft", return_value=draft):
            response = self.client.post(f"/accounting/documents/drafts/{draft.pk}/issue/", follow=True)
        page = self.assert_ok(response)
        self.assertEqual(response.redirect_chain[-1][0], OUTGOING)
        self.assertEqual(len(self.messages_of(response)), 1)
        self.assertIn(str(DocumentKind.INVOICE.label)[:3], page)  # the list of documents
        self.assertEqual(Document.objects.count(), 1)

    def test_the_second_call_for_a_gone_draft_is_a_404(self) -> None:
        draft = self.make_draft()
        free.issue(draft)
        self.assertEqual(self.client.post(f"/accounting/documents/drafts/{draft.pk}/issue/").status_code, 404)


class ReviewFreeApiTests(FreeData, ApiTestCase):
    """What the API accepted and the browser refuses, and the 500s found by the review."""

    def setUp(self) -> None:
        super().setUp()
        self.build()
        self.drafts = f"{API}/accounting/documents/drafts"

    def create(self, **fields: Any) -> dict[str, Any]:
        body = {"kind": "invoice", "customer": self.customer.pk, **fields}
        response = self.admin.post(self.drafts, body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def address(self, customer: Any, kind: str) -> Any:
        from rentalars.customers.models import CustomerAddress

        return CustomerAddress.objects.create(customer=customer, kind=kind, street="Hafenstr. 1", city="Köln")

    def test_null_for_the_descriptions_means_what_the_template_says(self) -> None:
        template = services.template_for(DocumentKind.INVOICE)
        template.print_product_descriptions = True
        template.save()
        draft = self.create(print_product_descriptions=False)
        self.assertFalse(draft["print_product_descriptions"])
        response = self.admin.patch(f"{self.drafts}/{draft['id']}", {"print_product_descriptions": None}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["print_product_descriptions"])
        self.assertTrue(DocumentDraft.objects.get().print_product_descriptions)

    def test_null_for_the_service_does_not_break_a_draft(self) -> None:
        draft = self.create()
        update = free.update_draft(DocumentDraft.objects.get(), introduction=None, closing=None, text_block_ids=None)
        self.assertEqual((update.introduction, update.closing, update.text_block_ids), ("", "", []))
        self.assertTrue(draft)

    def test_only_billing_addresses_of_the_customer_are_taken(self) -> None:
        from rentalars.customers.models import AddressKind

        draft = self.create()
        url = f"{self.drafts}/{draft['id']}"
        delivery = self.address(self.customer, AddressKind.DELIVERY)
        other = self.address(make_customer("Anderer"), AddressKind.BILLING)
        mine = self.address(self.customer, AddressKind.BILLING)
        for refused in (delivery, other):
            self.assert_error(
                self.admin.patch(url, {"billing_address": refused.pk}, format="json"),
                400,
                "validation_error",
                "billing_address",
            )
            self.assert_error(
                self.admin.post(
                    self.drafts,
                    {"kind": "offer", "customer": self.customer.pk, "billing_address": refused.pk},
                    format="json",
                ),
                400,
                "validation_error",
                "billing_address",
            )
        accepted = self.admin.patch(url, {"billing_address": mine.pk}, format="json")
        self.assertEqual((accepted.status_code, accepted.json()["billing_address"]), (200, mine.pk))

    def test_the_service_refuses_a_delivery_address_too(self) -> None:
        from rentalars.customers.models import AddressKind

        delivery = self.address(self.customer, AddressKind.DELIVERY)
        with self.assertRaises(ValidationError) as caught:
            free.create_draft(self.customer, DocumentKind.OFFER, billing_address=delivery)
        self.assertIn("billing_address", caught.exception.message_dict)

    def test_the_end_of_the_service_needs_its_start(self) -> None:
        draft = self.create()
        url = f"{self.drafts}/{draft['id']}"
        self.assert_error(
            self.admin.patch(url, {"service_end": "2027-03-20"}, format="json"), 400, "validation_error", "service_end"
        )
        ok = self.admin.patch(url, {"service_start": "2027-03-10", "service_end": "2027-03-20"}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assert_error(
            self.admin.post(
                self.drafts,
                {"kind": "invoice", "customer": self.customer.pk, "service_end": "2027-03-20"},
                format="json",
            ),
            400,
            "validation_error",
            "service_end",
        )

    def test_the_list_is_paged_like_the_others(self) -> None:
        for number in range(3):
            self.create(reference=f"Beleg {number}")
        page = self.admin.get(self.drafts, {"page_size": 2}).json()
        self.assertEqual((page["count"], len(page["results"])), (3, 2))
        self.assertIsNotNone(page["next"])
        second = self.admin.get(self.drafts, {"page_size": 2, "page": 2}).json()
        self.assertEqual(len(second["results"]), 1)

    def test_a_draft_issued_a_moment_ago_is_a_409_not_a_500(self) -> None:
        from rentalars.documents import free_api

        draft = self.create(lines=[{"title": "Aufbau", "unit_price": "10.00"}])
        stored = DocumentDraft.objects.get(pk=draft["id"])
        free.issue(stored)
        with mock.patch.object(free_api._FreeView, "draft", return_value=stored):
            response = self.admin.post(f"{self.drafts}/{draft['id']}/issue", {}, format="json")
        self.assert_error(response, 409, "already_issued")
        self.assert_error(self.admin.post(f"{self.drafts}/{draft['id']}/issue", {}, format="json"), 404, "not_found")

    def test_a_subject_with_line_breaks_is_one_line(self) -> None:
        configure_mailbox()
        document = self.issue()
        with capture_smtp() as sent:
            response = self.admin.post(
                f"{API}/accounting/documents/{document.pk}/send",
                {"to": "kasse@buehnenwerk.example", "subject": "Rechnung\r\nBcc: fremd@example.org\nzwei"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        (message,) = sent
        self.assertEqual(message["Subject"], "Rechnung Bcc: fremd@example.org zwei")
        self.assertIsNone(message["Bcc"])

    def test_an_anonymised_customer_gets_no_mail(self) -> None:
        configure_mailbox()
        document = self.issue()
        customer_services.anonymise_customer(self.customer)
        with capture_smtp() as sent:
            response = self.admin.post(
                f"{API}/accounting/documents/{document.pk}/send", {"to": "kasse@buehnenwerk.example"}, format="json"
            )
        self.assert_error(response, 400, "validation_error")
        self.assertEqual(sent, [])
        document.refresh_from_db()
        self.assertIsNone(document.sent_at)


class ReviewFreeMailTests(FreeCase):
    """The mail of a free document: one-line subject, nothing for an anonymised customer."""

    def test_the_form_makes_the_subject_one_line(self) -> None:
        configure_mailbox()
        document = self.issue()
        url = f"/accounting/documents/{document.pk}/send/"
        data = form_data(self.client.get(url), to="kasse@buehnenwerk.example", cc="", bcc="")
        data["subject"] = "Rechnung\nBcc: fremd@example.org"
        with capture_smtp() as sent:
            response = self.client.post(url, data)
        self.assertRedirects(response, f"/accounting/documents/{document.pk}/")
        self.assertEqual(sent[0]["Subject"], "Rechnung Bcc: fremd@example.org")
        self.assertIsNone(sent[0]["Bcc"])

    def test_the_service_makes_the_subject_one_line_whoever_calls_it(self) -> None:
        from rentalars.documents import free_mail

        configure_mailbox()
        document = self.issue()
        with capture_smtp() as sent:
            free_mail.send_document_mail(document, to="a@b.example", subject=" \n ", body="Hallo")
        self.assertEqual(sent[0]["Subject"], f"{document.title} {document.number}")

    def test_an_anonymised_customer_gets_no_mail_from_the_page(self) -> None:
        configure_mailbox()
        document = self.issue()
        customer_services.anonymise_customer(self.customer)
        url = f"/accounting/documents/{document.pk}/send/"
        data = form_data(self.client.get(url), to="kasse@buehnenwerk.example", cc="", bcc="", subject="x", body="y")
        with capture_smtp() as sent:
            response = self.client.post(url, data)
        self.assertEqual((response.status_code, sent), (200, []))
        document.refresh_from_db()
        self.assertIsNone(document.sent_at)

    def test_a_project_mail_subject_is_one_line_too(self) -> None:
        configure_mailbox()
        project = make_project("Sommerfest", customer=self.customer)
        url = f"/projects/{project.number}/mails/new/"
        data = form_data(self.client.get(url), "subject", to="kunde@kunde.example", subject="x", body="Hallo")
        data["subject"] = "Angebot\nBcc: fremd@example.org"
        with capture_smtp() as sent:
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:300])
        self.assertIn("Angebot Bcc: fremd@example.org", sent[0]["Subject"])
        self.assertIsNone(sent[0]["Bcc"])


class ReviewCustomerTests(FreeCase):
    """The customer's data: export, deleting, the log of what was looked at, buyer reference, rights."""

    def test_the_export_lists_free_documents_and_drafts(self) -> None:
        document = self.issue(reference="Sommerfest 2027")
        offer = self.make_draft(DocumentKind.OFFER, reference="Messe")
        shown = customer_services.export_customer(self.customer)
        self.assertEqual(
            shown["documents"],
            [
                {
                    "number": document.number,
                    "kind": "Rechnung",
                    "date": document.issued_on.isoformat(),
                    "total": "476.00",
                    "reference": "Sommerfest 2027",
                }
            ],
        )
        self.assertEqual(
            shown["drafts"],
            [{"number": "", "kind": "Angebot", "date": "2027-03-01", "total": "476.00", "reference": "Messe"}],
        )
        self.assertTrue(offer)
        # Documents of projects are in the list of the projects, not here; another customer's are not here at all.
        other = make_customer("Anderer")
        self.assertEqual((customer_services.export_customer(other)["documents"], customer_services.export_customer(other)["drafts"]), ([], []))  # fmt: skip

    def test_the_export_through_the_page_and_the_api(self) -> None:
        self.issue()
        page = self.client.get(reverse("customers:export", args=[self.customer.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertIn("RE-2027-0001", page.content.decode())

    def test_a_customer_with_only_drafts_or_documents_gets_a_clear_message(self) -> None:
        self.make_draft()
        with self.assertRaises(ValidationError) as caught:
            customer_services.delete_customer(self.customer)
        drafts_message = " ".join(caught.exception.messages)
        free.discard_drafts_of(self.customer)
        self.issue()
        with self.assertRaises(ValidationError) as again:
            customer_services.delete_customer(self.customer)
        self.assertEqual(" ".join(again.exception.messages), drafts_message)
        # With a project the old message stays.
        make_project("Sommerfest", customer=self.customer)
        with self.assertRaises(ValidationError) as with_project:
            customer_services.delete_customer(self.customer)
        self.assertNotEqual(" ".join(with_project.exception.messages), drafts_message)

    def test_the_buyer_reference_is_the_leitweg_id_or_the_customer_number(self) -> None:
        """As for a project (customer.buyer_reference or project.number): never the free text of the reference."""
        draft = self.make_draft(reference="Hire of a PA system")
        self.assertEqual(free.build_content(draft, number="").buyer_reference, self.customer.number)
        self.customer.buyer_reference = "04011000-1234512345-06"
        self.customer.save()
        self.assertEqual(free.build_content(draft, number="").buyer_reference, "04011000-1234512345-06")
        document = free.issue(draft)
        self.assertIn("04011000-1234512345-06", open_xml(document))

    def test_the_log_of_what_was_looked_at(self) -> None:
        from django.urls import resolve

        from rentalars.core import access_log

        document = self.issue()
        draft = self.make_draft(DocumentKind.OFFER)
        for name, args, kind in (
            ("documents:free_document", [document.pk], "document"),
            ("documents:free_send", [document.pk], "document"),
            ("documents:free_edit", [draft.pk], "draft"),
            ("documents:free_preview", [draft.pk], "draft"),
        ):
            with self.subTest(name=name):
                reference = access_log.reference_of(resolve(reverse(name, args=args)))
                self.assertEqual(reference, (kind, str(args[0])))

    def test_reading_a_document_or_draft_is_in_the_access_log_under_the_customer(self) -> None:
        from rentalars.core.models import AccessLogEntry

        document = self.issue()
        draft = self.make_draft(DocumentKind.OFFER)
        self.assertEqual(self.client.get(f"/accounting/documents/{document.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/accounting/documents/drafts/{draft.pk}/").status_code, 200)
        entries = list(AccessLogEntry.objects.order_by("id"))
        self.assertEqual(
            [(entry.object_type, entry.object_id) for entry in entries],
            [("document", str(document.pk)), ("customer", str(self.customer.pk))],
        )
        self.assertEqual(entries[0].parent_id, str(self.customer.pk))
        self.assertIn(self.customer.number, entries[1].label)
        # The same draft again within minutes is no second entry.
        self.client.get(f"/accounting/documents/drafts/{draft.pk}/")
        self.assertEqual(AccessLogEntry.objects.count(), 2)

    def test_the_rights_of_the_projects_are_enough_to_choose_a_customer(self) -> None:
        """Whoever may change free documents may write every project, and so reads the customers the project pages
        show – the helper needs no extra check, as the project pages have none."""
        from rentalars.projects.tables import may_see_customers

        maker = role("Nur Projekte", {"projects": 2, "customers": 0}, ["prices"])
        user = _user_with("pia", maker)
        browser = self.browser_of(user)
        rights = rights_of(user)
        self.assertTrue(free.may_change(rights))
        self.assertTrue(may_see_customers(rights))
        self.assertEqual(browser.get(NEW).status_code, 200)
        self.assertEqual(browser.get(reverse("customers:suggest"), {"q": "Bühnen"}).status_code, 200)
        response = browser.post(NEW, {"kind": "offer", "customer": self.customer.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DocumentDraft.objects.get().customer, self.customer)


def open_xml(document: Document) -> str:
    """The XRechnung of a document as text."""
    with document.xml_file.open("rb") as handle:
        return handle.read().decode()


class ReviewDocumentMigrationTests(TransactionTestCase):
    """DOK-022: the update of the documents and the way back (MariaDB cannot undo half a migration)."""

    before = [("documents", "0001_squashed_0006_statements_090")]
    after = [("documents", "0007_free_documents_095")]

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrate(self, targets: list[tuple[str, str]]) -> Any:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tables(self) -> set[str]:
        return set(connection.introspection.table_names())

    def columns(self, table: str) -> set[str]:
        with connection.cursor() as cursor:
            return {column.name for column in connection.introspection.get_table_description(cursor, table)}

    def applied(self) -> bool:
        return self.after[0] in MigrationExecutor(connection).loader.applied_migrations

    def free_document(self, apps_: Any, customer: Any) -> Any:
        return apps_.get_model("documents", "Document").objects.create(
            project=None,
            customer_id=customer.pk,
            kind="offer",
            number="AN-2027-0001",
            title="Angebot",
            issued_on=datetime.date(2027, 3, 1),
            file="documents/free/AN-2027-0001.pdf",
            sha256="0" * 64,
        )

    def test_back_and_forth_without_free_documents(self) -> None:
        self.migrate(self.after)
        self.assertIn("documents_documentdraft", self.tables())
        self.migrate(self.before)
        self.assertNotIn("documents_documentdraft", self.tables())
        self.assertNotIn("customer_id", self.columns("documents_document"))
        self.assertFalse(self.applied())
        self.migrate(self.after)
        self.assertIn("documents_documentdraft", self.tables())
        self.assertTrue(self.applied())

    def test_going_back_with_a_free_document_is_refused_and_changes_nothing(self) -> None:
        customer = make_customer("Bühnenwerk")
        new = self.migrate(self.after)
        self.free_document(new, customer)
        with self.assertRaises(IrreversibleError) as caught:
            self.migrate(self.before)
        self.assertIn("without a project", str(caught.exception))
        # Nothing was changed: the tables, the column and the entry that the migration is applied.
        self.assertIn("documents_documentdraft", self.tables())
        self.assertIn("documents_draftline", self.tables())
        self.assertIn("customer_id", self.columns("documents_document"))
        self.assertTrue(self.applied())
        self.assertEqual(new.get_model("documents", "Document").objects.filter(project__isnull=True).count(), 1)
        # Once the document is gone the way back is open.
        new.get_model("documents", "Document").objects.all().delete()
        self.migrate(self.before)
        self.assertNotIn("documents_documentdraft", self.tables())

    def test_documents_of_projects_do_not_stop_the_way_back(self) -> None:
        customer = make_customer("Bühnenwerk")
        project = make_project("Sommerfest", customer=customer)
        new = self.migrate(self.after)
        new.get_model("documents", "Document").objects.create(
            project_id=project.pk,
            customer_id=customer.pk,
            kind="offer",
            number="AN-2027-0002",
            title="Angebot",
            issued_on=datetime.date(2027, 3, 1),
            file="documents/1/AN-2027-0002.pdf",
            sha256="0" * 64,
        )
        old = self.migrate(self.before)
        self.assertEqual(old.get_model("documents", "Document").objects.count(), 1)

    def test_the_customer_comes_from_the_frozen_content_first(self) -> None:
        theater = make_customer("Theater am Markt")
        works = make_customer("Stadtwerke")
        project = make_project("Stadtfest", customer=theater)
        old = self.migrate(self.before)
        documents = old.get_model("documents", "Document").objects

        def stored(number: str, content: dict[str, Any]) -> None:
            documents.create(
                project_id=project.pk,
                kind="offer",
                number=number,
                title="Angebot",
                issued_on=datetime.date(2027, 3, 1),
                file=f"documents/{project.pk}/{number}.pdf",
                sha256="0" * 64,
                content=content,
            )

        # The project belonged to the theater when the first was made; it has been given to the works since.
        stored("AN-2027-0001", {"customer_number": theater.number})
        stored("AN-2027-0002", {"customer_number": works.number})
        stored("AN-2027-0003", {})  # no number in the content: the customer of the project
        stored("AN-2027-0004", {"customer_number": "99999"})  # a customer that does not exist (any more)
        stored("AN-2027-0005", {"customer_number": ""})
        new = self.migrate(self.after)
        found = dict(new.get_model("documents", "Document").objects.values_list("number", "customer_id"))
        self.assertEqual(
            found,
            {
                "AN-2027-0001": theater.pk,
                "AN-2027-0002": works.pk,
                "AN-2027-0003": theater.pk,
                "AN-2027-0004": theater.pk,
                "AN-2027-0005": theater.pk,
            },
        )
