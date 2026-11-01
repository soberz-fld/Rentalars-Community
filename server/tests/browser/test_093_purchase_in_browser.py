# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: "Kauf einpflegen" starts with one row, "Weitere Position" adds one at once, and the sum
of the positions follows what is typed (MAT-075; MAT-061, MAT-059).

The requirements: "Kauf einpflegen" shows only one position by default, further ones are created by the AI or by the
operator; below, the sum (net and gross) of the entered positions is shown for cross-checking.

The page tests (tests/unit/test_093_purchase.py) read the sum the server renders; only a browser runs the script
that recomputes it while typing – the same numbers, in the same format.
"""

from __future__ import annotations

from unittest import SkipTest

from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import make_model
from tests.unit.test_091_purchase import FilesMixin, pdf_of
from tests.unit.test_093_purchase import INVOICE_LINES

URL = "/material/purchase/"


class PurchaseInBrowserTests(FilesMixin, BrowserTestCase):
    """One row to begin with, a row more at once, the sum while typing (MAT-075)."""

    bypass_csp = True  # axe-core is added to the page as a script

    def setUp(self) -> None:
        super().setUp()
        make_model("Mischpult 093", category_code="T")

    def axe_findings(self) -> list[str]:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.wait_for_load_state("networkidle")
        self.page.add_script_tag(path=str(axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def sum_reads(self, expected: str) -> None:
        """Wait until the line of the sum reads ``expected`` (the script waits a moment after the last key)."""
        self.page.wait_for_function(
            "(text) => document.querySelector('.purchase-sum-line').innerText.replace(/\\s+/g, ' ').includes(text)",
            arg=expected,
        )

    def test_rows_and_the_sum_while_typing(self) -> None:
        self.open(URL)
        rows = self.page.locator("[data-formset-rows] [data-formset-row]")
        self.assertEqual(rows.count(), 1)
        self.assertTrue(self.page.locator("[data-purchase-more]").is_hidden())
        self.sum_reads("0,00 € netto · 0,00 € brutto")

        self.page.fill("#id_pos-0-model_name", "Mischpult 093")
        self.page.fill("#id_pos-0-count", "2")
        self.page.fill("#id_pos-0-unit_price", "1.072,50")
        self.sum_reads("2.145,00 € netto · 2.552,55 € brutto")

        self.page.locator("[data-formset-add]").click()
        self.assertEqual(rows.count(), 2)
        self.assertEqual(self.page.evaluate("() => document.activeElement.name"), "pos-1-model_name")
        self.page.keyboard.type("Neues Pult")
        unpriced = self.page.locator("[data-sum-unpriced]")
        unpriced.wait_for()
        self.assertEqual(unpriced.inner_text(), "1 Position ohne Preis – sie zählt mit 0.")
        self.assertEqual(self.axe_findings(), [])

        # Removing the row takes it out of the sum.
        rows.nth(1).locator("button", has_text="Zeile entfernen").click()
        unpriced.wait_for(state="hidden")
        # Gross prices (MAT-059): the gross sum adds them, the net sum what is stored – each price net, in cents.
        self.page.select_option("#id_prices", "gross")
        self.sum_reads("1.802,52 € netto · 2.145,00 € brutto")
        self.page.check("#id_pos-0-price_for_set")
        self.sum_reads("901,26 € netto · 1.072,50 € brutto")

    def test_the_difference_to_the_invoice_while_typing(self) -> None:
        self.open(URL)
        self.page.set_input_files(
            "#id_invoice",
            files=[{"name": "rechnung.pdf", "mimeType": "application/pdf", "buffer": pdf_of(INVOICE_LINES)}],
        )
        self.page.locator("button[value=read]").click()
        self.page.wait_for_load_state()
        difference = self.page.locator("[data-sum-difference]")
        self.assertEqual(difference.inner_text(), "-1.571,40 €")
        self.page.fill("#id_pos-0-model_name", "Mischpult 093")
        self.page.fill("#id_pos-0-unit_price", "1.320,50")
        self.page.wait_for_function(
            "() => document.querySelector('[data-sum-difference]').innerText === 'stimmt überein'"
        )
        self.page.fill("#id_pos-0-unit_price", "1.320,00")
        self.page.wait_for_function("() => document.querySelector('[data-sum-difference]').innerText === '-0,60 €'")
