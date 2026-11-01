# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: an incoming invoice from the upload to the items (Buchhaltung → Eingangsrechnungen). (DOK-023, DOK-024)

The requirements: a management of incoming invoices (in Buchhaltung) including AI recognition; items or quantities of
bulk material can be created from incoming invoices; transport costs are spread ("aufteilen") as ancillary acquisition
costs. Page, service and API tests are in tests/unit/test_100_incoming.py; here the interplay with the scripts
of the pages: the upload, the rows that are added, the preview of the ancillary costs that follows the key without a page
load, and the booking in with its explicit confirmation, with the accessibility check of both pages.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from rentalars.incoming.models import IncomingInvoice
from rentalars.material.models import MaterialItem
from tests.browser.base import BrowserTestCase
from tests.browser.test_100_products_planning_in_browser import AxeMixin
from tests.helpers import make_model
from tests.unit.test_091_purchase import FilesMixin, pdf_of
from tests.unit.test_100_incoming import INCOMING_LINES


class IncomingInvoiceInBrowserTests(AxeMixin, FilesMixin, BrowserTestCase):
    """The main way through the register: upload, correct, mark the freight, look at the cost, book in."""

    bypass_csp = True  # axe-core is put into the page

    def setUp(self) -> None:
        super().setUp()
        self.mic = make_model("Shure SM58", category_code="T", manufacturer="Shure")

    def add_position(self, description: str, amount: str, kind: str = "goods") -> None:
        """Save the invoice with an empty row, fill the row, save again – as a person adds positions one by one.

        A row asks for the net amount of the whole position; the number of pieces is chosen when booking in.
        """
        self.page.locator("button[name=action][value=add]").click()
        row = self.page.locator("#new-position")
        row.wait_for()
        row.locator("input[name$=-description]").fill(description)
        row.locator("input[name$=-amount_net]").fill(amount)
        row.locator("select[name$=-position_type]").select_option(kind)
        self.page.locator("button[name=action][value=save]").click()
        row.wait_for(state="detached")  # saved: the page is shown anew without the empty row
        self.page.get_by_text("Die Rechnung ist gespeichert.").wait_for()

    def test_from_the_upload_to_the_items(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        pdf = folder / "rechnung.pdf"
        pdf.write_bytes(pdf_of(INCOMING_LINES))

        # Upload: the invoice is read at once; number, date and totals stand in the form.
        self.open("/accounting/incoming/capture/")
        self.assertEqual(self.axe_findings("main"), [])
        self.page.set_input_files("input[type=file]", str(pdf))
        self.page.get_by_role("button", name="Hochladen und auslesen").click()
        self.page.wait_for_url(re.compile(r".*/accounting/incoming/\d+/\?asked=book$"))
        self.assertIn("Auch in der Materialverwaltung einpflegen?", self.text_of("main"))
        invoice = IncomingInvoice.objects.get()
        self.assertEqual(self.page.locator("#id_invoice_number").input_value(), "RE-2027-0815")
        self.assertEqual(self.page.locator("#id_invoice_date").input_value(), "2027-02-22")
        self.assertIn("aus dem Text gelesen", self.text_of("#incoming-reading"))

        # Correct something, add a note, add the positions: two goods and the freight.
        self.page.locator("#id_note").fill("Mikrofone und Kabel für die Sommertour")
        self.page.locator("#id_status").select_option("checked")
        self.add_position("Shure SM58", "297,00")
        self.add_position("Neutrik NL4 Kabel 10 m", "50,00")
        self.add_position("Fracht und Verpackung", "30,00", kind="ancillary")
        invoice.refresh_from_db()
        self.assertEqual((invoice.note, invoice.status), ("Mikrofone und Kabel für die Sommertour", "checked"))
        self.assertEqual(invoice.positions.count(), 3)

        # The sum under the Kontierungen is worked out while typing, nothing is saved by that.
        self.page.locator("#position-" + str(invoice.positions.first().pk) + " input[name$=-amount_net]").fill("300,00")
        self.page.get_by_text("Die Kontierungen ergeben zusammen 380,00").wait_for()
        invoice.refresh_from_db()
        self.assertEqual(invoice.positions.first().line_net, Decimal("297.00"))
        self.page.reload()

        # The freight is spread by value; another key changes the preview at once, without leaving the page.
        costing = self.page.locator("#costing")
        self.assertIn("322,68", " ".join(costing.inner_text().split()).replace("\xa0", " "))
        self.page.locator("#id_allocation_key").select_option("quantity")
        self.settle()
        # Typed by hand a position is one piece: by quantity each of the two takes half of the freight.
        self.assertIn("312,00", " ".join(costing.inner_text().split()).replace("\xa0", " "))  # 297 + 15
        self.page.locator("#id_allocation_key").select_option("value")
        self.settle()
        self.assertIn("322,68", " ".join(costing.inner_text().split()).replace("\xa0", " "))
        invoice.refresh_from_db()
        self.assertEqual(invoice.allocation_key, "value")  # looking at a key saved nothing
        self.assertEqual(self.axe_findings("main"), [])

        # Book in: choose the model, look at the preview, confirm.
        self.page.get_by_role("link", name="Ware einpflegen").click()
        self.page.wait_for_url("**/book/")
        self.page.locator("#id_pos-1-include").uncheck()  # the cables are another time
        self.page.locator("#id_pos-0-count").fill("3")  # the number of pieces is chosen here
        self.page.locator("#id_pos-0-asset_kind").select_option("merchandise")  # The kind is confirmed, not guessed
        self.assertEqual(self.axe_findings("main"), [])
        self.page.get_by_role("button", name="Vorschau zeigen").click()
        self.page.locator("#preview").wait_for()
        self.assertIn("322,68", self.text_of("#preview").replace("\xa0", " "))
        self.assertEqual(
            MaterialItem.objects.filter(source_position__isnull=False).count(), 0
        )  # a preview makes nothing
        self.page.get_by_role("button", name="Einpflegen", exact=True).click()
        self.page.wait_for_selector("[role=status], .message")
        self.assertEqual(
            MaterialItem.objects.filter(source_position__isnull=False).count(), 0
        )  # not confirmed: nothing is made
        self.page.get_by_label("Ja, genau so einpflegen").check()
        self.page.get_by_role("button", name="Einpflegen", exact=True).click()
        self.page.wait_for_url(f"**/accounting/incoming/{invoice.pk}/")
        self.assertIn("Eingepflegt", self.text_of("body"))
        items = list(MaterialItem.objects.filter(source_position__isnull=False).order_by("inventory_number"))
        self.assertEqual(len(items), 3)
        self.assertEqual({item.acquisition_cost_net for item in items}, {Decimal("107.56")})
        self.assertEqual({item.material_model for item in items}, {self.mic})
        self.assertIn("eingepflegt", self.text_of("#position-" + str(items[0].source_position_id)))
        self.assertEqual(self.axe_findings("main"), [])
