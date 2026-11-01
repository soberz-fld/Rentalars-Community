# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of the documents of a project: DOK-003, DOK-004, DOK-005, DOK-006, DOK-007, DOK-008, DOK-009."""

from __future__ import annotations

from django.urls import reverse

from rentalars.documents import services
from rentalars.documents.models import Document, DocumentKind, TextBlock
from tests.helpers import add_line, make_project, make_stock, ready_for_invoices
from tests.mailbox import capture_smtp, configure_mailbox
from tests.ui.base import UiTestCase, form_data


def content_of(response: object) -> bytes:
    """The body of a file response, streamed or not."""
    streamed = getattr(response, "streaming_content", None)
    return b"".join(streamed) if streamed is not None else response.content  # type: ignore[attr-defined]


class DocumentPageTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=ready_for_invoices())
        add_line(self.project, make_stock("L-010", 6, "PAR 64", price="20.00"), 4)
        self.url = reverse("documents:list", args=[self.project.pk])

    def test_draft_make_and_cancel_an_invoice(self) -> None:
        TextBlock.objects.create(name="Mietbedingungen", text="Es gelten unsere Mietbedingungen.")
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Noch keine Dokumente.", page)
        self.assertIn("Mietbedingungen", page)
        data = form_data(self.client.get(self.url), "kind", kind="invoice")

        draft = self.client.post(reverse("documents:preview", args=[self.project.pk]), data)
        self.assertTrue(draft.content.startswith(b"%PDF"))
        self.assertFalse(Document.objects.exists())

        made = self.client.post(reverse("documents:create", args=[self.project.pk]), data, follow=True)
        self.assertIn("Rechnung RE-2027-0001 erstellt.", self.messages_of(made))
        invoice = Document.objects.get()
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("XRechnung", page)
        self.assertIn(f"?document={invoice.pk}", page)
        self.assertTrue(content_of(self.client.get(reverse("documents:file", args=[invoice.pk]))).startswith(b"%PDF"))
        self.assertIn(b"RE-2027-0001", content_of(self.client.get(reverse("documents:xml", args=[invoice.pk]))))

        again = self.client.post(reverse("documents:create", args=[self.project.pk]), data, follow=True)
        self.assertIn(
            "Rechnung RE-2027-0001 dieses Projekts ist noch gültig. Storniere sie zuerst.", self.messages_of(again)
        )
        cancelled = self.client.post(reverse("documents:cancel", args=[invoice.pk]), follow=True)
        self.assertIn("Rechnung RE-2027-0001 ist durch RE-2027-0002 storniert.", self.messages_of(cancelled))
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("storniert RE-2027-0001", page)
        twice = self.client.post(reverse("documents:cancel", args=[invoice.pk]), follow=True)
        self.assertIn("Diese Rechnung ist bereits storniert.", self.messages_of(twice))

    def test_warehouse_sees_only_documents_without_prices(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        services.create_document(self.project, DocumentKind.DELIVERY_NOTE)
        warehouse = self.browser_for("luka", "Lager")
        page = self.assert_ok(warehouse.get(self.url))
        self.assertIn("LS-2027-0001", page)
        self.assertNotIn("RE-2027-0001", page)
        self.assertNotIn("Dokument erstellen", page)
        self.assertEqual(warehouse.get(reverse("documents:file", args=[invoice.pk])).status_code, 403)
        self.assertEqual(
            warehouse.post(reverse("documents:create", args=[self.project.pk]), {"kind": "delivery_note"}).status_code,
            403,
        )

    def test_send_a_document_by_mail(self) -> None:
        configure_mailbox()
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        compose = f"/projects/{self.project.pk}/mails/new/"
        # DOK-044: the XML goes along when the customer has a buyer reference (the invoice is for an authority)
        self.project.customer.buyer_reference = "04011000-12345-34"
        self.project.customer.save()
        data = form_data(self.client.get(compose, {"document": invoice.pk}), "subject")
        self.assertEqual(data["documents"], [f"doc:{invoice.pk}", f"xml:{invoice.pk}"])
        self.assertTrue(data["subject"].startswith("Rechnung RE-2027-0001"))
        data.update(to="einkauf@stadtwerke.example", body="Anbei die Rechnung.")
        with capture_smtp() as sent:
            self.client.post(compose, data, follow=True)
        (message,) = sent
        self.assertEqual(
            sorted(part.get_filename() for part in message.iter_attachments()),
            ["RE-2027-0001.xml", "Rechnung-RE-2027-0001.pdf"],
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.sent_to, "einkauf@stadtwerke.example")
        self.assertIn("einkauf@stadtwerke.example", self.assert_ok(self.client.get(self.url)))

    def test_price_overview_as_files(self) -> None:
        pdf = self.client.get(reverse("projects:price_overview_pdf", args=[self.project.pk]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        csv = self.client.get(reverse("projects:price_overview_csv", args=[self.project.pk]), {"detail": "groups"})
        self.assertIn("attachment", csv["Content-Disposition"])
        self.assertTrue(csv.content.decode("utf-8-sig").startswith("Bereich;Inhalt;Betrag"))
        page = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        self.assertIn(reverse("projects:price_overview_csv", args=[self.project.pk]), page)
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.get(reverse("projects:price_overview_pdf", args=[self.project.pk])).status_code, 403)

    def test_templates_and_text_blocks_in_the_administration(self) -> None:
        page = self.assert_ok(self.client.get("/administration/"))
        templates = reverse("admin:documents_documenttemplate_changelist")
        blocks = reverse("admin:documents_textblock_changelist")
        self.assertIn(templates, page)
        self.assertIn(blocks, page)
        self.assertIn("Auftragsbestätigung", self.assert_ok(self.client.get(templates)))
        add = reverse("admin:documents_textblock_add")
        self.client.post(
            add, {"name": "Haftung", "text": "Haftung nach Mietbedingungen.", "kinds": ["invoice"], "is_active": "on"}
        )
        self.assertEqual(TextBlock.objects.get().kinds, ["invoice"])
