# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the advance, partial and final invoices and the partial credit notes on the tab "Dokumente"."""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.documents import services
from rentalars.documents.billing import Billing
from rentalars.documents.models import BillingType, Document, DocumentKind
from tests.helpers import add_line, make_project, make_stock, ready_for_invoices
from tests.ui.base import UiTestCase, form_data


class BillingPageTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=ready_for_invoices())
        add_line(self.project, make_stock("L-010", 6, "PAR 64", price="100.00"), 10)  # net 1.500,00
        self.url = reverse("documents:list", args=[self.project.pk])
        self.create = reverse("documents:create", args=[self.project.pk])

    def invoice_form(self, **changes: str) -> dict[str, object]:
        return form_data(self.client.get(self.url), "kind", kind="invoice", **changes)

    def test_the_form_offers_the_types_and_the_amount(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        options = page[page.index('class="billing-options"') :]
        self.assertTrue(options.startswith('class="billing-options" data-show-if="kind=invoice"'))
        for text in (
            "Abschlagsrechnung",
            "Teilrechnung",
            "Schlussrechnung",
            'name="billing_percent"',
            'name="billing_amount"',
            'name="billing_note"',
            'data-show-if="kind=invoice&amp;billing_type=advance|partial"'.replace("&amp;", "&"),
        ):
            self.assertIn(text, options)
        self.assertNotIn("Abrechnungsstand", page)  # nothing billed yet: no status panel

    def test_an_advance_invoice_is_made_and_the_status_shows(self) -> None:
        made = self.client.post(
            self.create,
            self.invoice_form(billing_type="advance", billing_percent="20", billing_note="Anzahlung"),
            follow=True,
        )
        self.assertIn("1. Abschlagsrechnung RE-2027-0001 erstellt.", self.messages_of(made))
        document = Document.objects.get()
        self.assertEqual((document.billing_type, document.net_total), ("advance", Decimal("300.00")))
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("data-billing-state", page)
        self.assertIn("Abrechnungsstand", page)
        self.assertIn("1.200,00", page)  # still to bill, net
        self.assertIn('data-billing-type="advance"', page)
        # the next step suggested is the final invoice
        form = form_data(self.client.get(self.url), "kind")
        self.assertEqual(form["billing_type"], "final")

    def test_a_refused_invoice_says_why(self) -> None:
        self.client.post(self.create, self.invoice_form(billing_type="advance", billing_percent="20"), follow=True)
        refused = self.client.post(self.create, self.invoice_form(billing_type=""), follow=True)
        self.assertIn("Schlussrechnung", " ".join(self.messages_of(refused)))
        self.assertEqual(Document.objects.count(), 1)
        too_much = self.client.post(
            self.create, self.invoice_form(billing_type="partial", billing_amount="2000,00"), follow=True
        )
        self.assertIn("höher als", " ".join(self.messages_of(too_much)))
        self.assertEqual(Document.objects.count(), 1)

    def test_a_partial_credit_note_is_made_from_the_list(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn(reverse("documents:credit", args=[invoice.pk]), page)
        made = self.client.post(
            reverse("documents:credit", args=[invoice.pk]), {"amount": "100,00", "note": "Rabatt"}, follow=True
        )
        self.assertIn("teilweise gutgeschrieben", " ".join(self.messages_of(made)))
        credit = Document.objects.get(credit_for=invoice)
        self.assertEqual((credit.net_total, credit.billing_type), (Decimal("-100.00"), BillingType.CREDIT))
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("schreibt", page)  # "schreibt RE-… gut"
        refused = self.client.post(reverse("documents:credit", args=[invoice.pk]), {"amount": "5000"}, follow=True)
        self.assertIn("höher als", " ".join(self.messages_of(refused)))
        self.assertEqual(Document.objects.filter(credit_for=invoice).count(), 1)

    def test_the_status_lists_credit_notes_of_part_invoices(self) -> None:
        part = services.create_document(
            self.project, DocumentKind.INVOICE, billing=Billing(type="partial", amount=Decimal("500"))
        )
        self.client.post(reverse("documents:credit", args=[part.pk]), {"percent": "10"}, follow=True)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("450,00", page)  # 500,00 less 10 %
