# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the advance, partial and final invoices and the partial credit notes (DOK-030 to DOK-036)."""

from __future__ import annotations

from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, make_project, make_stock, ready_for_invoices


class BillingApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=ready_for_invoices())
        add_line(
            self.project, make_stock("L-010", 6, "PAR 64", price="100.00"), 10
        )  # net 1.500,00 incl. rental days · gross 1.785,00
        self.url = f"{API}/projects/{self.project.pk}/documents"

    def make(self, **body: object) -> dict:
        response = self.admin.post(self.url, {"kind": "invoice", **body}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_advance_partial_final_and_credit(self) -> None:
        advance = self.make(billing_type="advance", percent="30.00", note="Anzahlung")
        self.assertEqual((advance["billing_type"], advance["billing_number"]), ("advance", 1))
        self.assertEqual((advance["net_total"], advance["gross_total"]), ("450.00", "535.50"))
        partial = self.make(billing_type="partial", amount="200.00")
        self.assertEqual(
            (partial["billing_type"], partial["billing_number"], partial["gross_total"]), ("partial", 2, "238.00")
        )

        # the draft follows the rules, and nothing is stored by it
        draft = self.admin.post(f"{self.url}/preview", {"kind": "invoice", "billing_type": "final"}, format="json")
        self.assertTrue(draft.content.startswith(b"%PDF"))
        # an ordinary invoice is refused while advance and partial invoices are valid
        self.assert_error(self.admin.post(self.url, {"kind": "invoice"}, format="json"), 400, "validation_error")
        # more than is left
        self.assert_error(
            self.admin.post(
                self.url, {"kind": "invoice", "billing_type": "advance", "amount": "900.00"}, format="json"
            ),
            400,
            "validation_error",
        )

        credit = self.admin.post(
            f"{API}/documents/{partial['id']}/credit", {"amount": "50.00", "note": "Weniger Aufbau"}, format="json"
        )
        self.assertEqual(credit.status_code, 201, credit.content)
        self.assertEqual(
            (credit.json()["credit_for"], credit.json()["billing_type"], credit.json()["gross_total"]),
            (partial["id"], "credit", "-59.50"),
        )
        self.assert_error(
            self.admin.post(
                f"{API}/documents/{partial['id']}/credit", {"percent": "100", "amount": "1"}, format="json"
            ),
            400,
            "validation_error",
        )

        final = self.make(billing_type="final")
        self.assertEqual(
            (final["billing_type"], final["gross_total"]), ("final", "1071.00")
        )  # what it adds after the deduction
        xml = self.admin.get(final["xml_url"])
        body = b"".join(xml.streaming_content)
        self.assertIn(b"PrepaidAmount", body)
        # under the final invoice the part invoices are neither credited nor cancelled
        self.assert_error(
            self.admin.post(f"{API}/documents/{advance['id']}/credit", {"percent": "10"}, format="json"),
            400,
            "validation_error",
        )
        self.assert_error(self.admin.post(f"{API}/documents/{advance['id']}/cancel"), 400, "validation_error")

    def test_the_rights_and_unknown_types(self) -> None:
        self.assert_error(
            self.admin.post(self.url, {"kind": "invoice", "billing_type": "weekly"}, format="json"),
            400,
            "validation_error",
            "billing_type",
        )
        advance = self.make(billing_type="advance", percent="10")
        warehouse = self.client_for("luka", "Lager")
        self.assert_error(
            warehouse.post(f"{API}/documents/{advance['id']}/credit", {"percent": "10"}, format="json"),
            403,
            "permission_denied",
        )
