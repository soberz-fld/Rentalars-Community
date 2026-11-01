# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the documents (DOK-003 to DOK-009)."""

from __future__ import annotations

from rentalars.core.models import CompanyProfile
from rentalars.documents import services
from rentalars.documents.models import DocumentKind
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, make_project, make_stock, ready_for_invoices


def body_of(response: object) -> bytes:
    """The body of a file response, streamed or not."""
    streamed = getattr(response, "streaming_content", None)
    return b"".join(streamed) if streamed is not None else response.content  # type: ignore[attr-defined]


class DocumentApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=ready_for_invoices())
        add_line(self.project, make_stock("L-010", 6, "PAR 64", price="20.00"), 4)
        self.url = f"{API}/projects/{self.project.pk}/documents"

    def test_make_fetch_and_cancel_an_invoice(self) -> None:
        block = self.admin.post(
            f"{API}/text-blocks", {"name": "Mietbedingungen", "text": "Es gelten unsere Bedingungen."}, format="json"
        )
        self.assertEqual(block.status_code, 201, block.content)
        draft = self.admin.post(
            f"{self.url}/preview", {"kind": "invoice", "text_blocks": [block.json()["id"]]}, format="json"
        )
        self.assertTrue(draft.content.startswith(b"%PDF"))
        self.assertEqual(self.admin.get(self.url).json(), [])

        made = self.admin.post(self.url, {"kind": "invoice", "text_blocks": [block.json()["id"]]}, format="json")
        self.assertEqual(made.status_code, 201, made.content)
        invoice = made.json()
        self.assertEqual((invoice["number"], invoice["gross_total"]), ("RE-2027-0001", "142.80"))
        self.assertEqual(self.admin.get(f"{API}/documents/{invoice['id']}").json()["number"], "RE-2027-0001")
        self.assertTrue(body_of(self.admin.get(invoice["pdf_url"])).startswith(b"%PDF"))
        self.assertIn(b"<cbc:ID>RE-2027-0001</cbc:ID>", body_of(self.admin.get(invoice["xml_url"])))
        self.assert_error(self.admin.post(self.url, {"kind": "invoice"}, format="json"), 400, "validation_error")

        cancelled = self.admin.post(f"{API}/documents/{invoice['id']}/cancel", format="json")
        self.assertEqual(cancelled.status_code, 201, cancelled.content)
        self.assertEqual((cancelled.json()["cancels"], cancelled.json()["gross_total"]), (invoice["id"], "-142.80"))
        self.assert_error(self.admin.post(f"{API}/documents/{invoice['id']}/cancel"), 400, "validation_error")
        self.assertEqual(
            [entry["number"] for entry in self.admin.get(self.url).json()][:2], ["RE-2027-0002", "RE-2027-0001"]
        )

    def test_documents_without_prices_and_the_rights(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(warehouse.get(self.url).json(), [])
        self.assert_error(warehouse.get(f"{API}/documents/{invoice.pk}"), 403, "permission_denied")
        self.assert_error(warehouse.post(self.url, {"kind": "delivery_note"}, format="json"), 403, "permission_denied")
        manager = self.client_for("paula", "Projektleitung")
        delivery = manager.post(self.url, {"kind": "delivery_note"}, format="json").json()
        self.assertEqual((delivery["number"], delivery["xml_url"]), ("LS-2027-0001", ""))
        self.assertEqual([entry["number"] for entry in warehouse.get(self.url).json()], ["LS-2027-0001"])
        self.assert_error(self.admin.get(f"{API}/documents/{delivery['id']}/xml"), 404, "not_found")
        self.assert_error(
            self.admin.post(self.url, {"kind": "cancellation"}, format="json"), 400, "validation_error", "kind"
        )

    def test_missing_company_data_stops_the_invoice(self) -> None:
        CompanyProfile.objects.update(email="")
        error = self.assert_error(
            self.admin.post(self.url, {"kind": "invoice"}, format="json"), 400, "validation_error"
        )
        self.assertIn("E-Mail-Adresse der Firma", error["message"])

    def test_templates_and_text_blocks(self) -> None:
        templates = self.admin.get(f"{API}/document-templates").json()
        self.assertEqual(len(templates), len(DocumentKind.values))
        confirmation = next(entry for entry in templates if entry["kind"] == "order_confirmation")
        url = f"{API}/document-templates/{confirmation['id']}"
        self.assertEqual(self.admin.get(url).json()["title"], "Auftragsbestätigung")
        changed = self.admin.patch(url, {"introduction": "Hallo {customer}!", "kind": "invoice"}, format="json").json()
        self.assertEqual((changed["introduction"], changed["kind"]), ("Hallo {customer}!", "order_confirmation"))
        replaced = self.admin.put(
            url,
            {"title": "Bestätigung", "introduction": "", "closing": "", "footer": "", "show_logo": False},
            format="json",
        )
        self.assertEqual(replaced.json()["title"], "Bestätigung")
        reader = self.client_for("nora", "Nur-Lesen")
        self.assertEqual(reader.get(url).status_code, 200)
        self.assert_error(reader.patch(url, {"title": "x"}, format="json"), 403, "permission_denied")

        blocks = f"{API}/text-blocks"
        created = self.admin.post(blocks, {"name": "Haftung", "text": "…", "kinds": ["invoice"]}, format="json").json()
        self.assert_error(
            # Not a kind of document ("offer" is one since DOK-010).
            self.admin.post(blocks, {"name": "x", "text": "y", "kinds": ["quotation"]}, format="json"),
            400,
            "validation_error",
            "kinds.0",
        )
        self.assertEqual(self.admin.get(f"{blocks}/{created['id']}").json()["kinds"], ["invoice"])
        self.admin.put(f"{blocks}/{created['id']}", {"name": "Haftung", "text": "Neu", "kinds": []}, format="json")
        self.admin.patch(f"{blocks}/{created['id']}", {"is_active": False}, format="json")
        self.assertEqual(
            [(entry["text"], entry["is_active"]) for entry in self.admin.get(blocks).json()], [("Neu", False)]
        )
        self.assertEqual(self.admin.delete(f"{blocks}/{created['id']}").status_code, 204)

    def test_price_overview_as_files(self) -> None:
        base = f"{API}/projects/{self.project.pk}/price-overview"
        self.assertTrue(self.admin.get(f"{base}/pdf").content.startswith(b"%PDF"))
        csv = self.admin.get(f"{base}/csv", {"detail": "groups"})
        self.assertTrue(csv.content.decode("utf-8-sig").startswith("Bereich;Inhalt;Betrag"))
        self.assert_error(self.client_for("luka", "Lager").get(f"{base}/csv"), 403, "permission_denied")
