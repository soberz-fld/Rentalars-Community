# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: "Etikett" of an item asks in a dialog, the choice prints that label at once (MAT-066).

The dialog loads over the item's page; a choice opens the print page of exactly that item and label in a tab of its
own, whose print dialog opens by itself (``window.print`` is replaced here and only counted). The label is set in
Liberation Sans, loaded from the server, and its QR code has the size the layout gives it. "Etiketten" of a model
leads to the page of the labels with its items.
"""

from __future__ import annotations

from rentalars.material import labels
from rentalars.material.label_layouts import LAYOUTS, lay_out
from rentalars.material.models import MaterialItem
from tests.browser.base import BrowserTestCase

#: CSS pixels per millimetre.
PX_PER_MM = 96 / 25.4


class LabelChoiceInBrowserTests(BrowserTestCase):
    """The dialog of an item and the print page it opens (MAT-066, MAT-065)."""

    def setUp(self) -> None:
        super().setUp()
        self.item = MaterialItem.objects.exclude(status__in=("retired", "sold", "lost")).order_by("pk").first()
        self.page.context.add_init_script(
            "window.__printed = 0; window.print = function () { window.__printed += 1; };"
        )

    def test_choose_and_print(self) -> None:
        self.open(f"/material/items/{self.item.pk}/")
        self.page.get_by_role("link", name="Etikett", exact=True).click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.wait_for()
        self.assertIn(f"Etikett für {self.item.display_id}", dialog.inner_text())
        choices = dialog.locator("[data-label-kind]")
        self.assertEqual(choices.count(), 6)
        with self.page.context.expect_page() as opened:
            dialog.locator('[data-label-kind="small"]').click()
        printed = opened.value
        printed.wait_for_load_state("networkidle")
        printed.wait_for_function("() => window.__printed > 0")  # the print dialog opened by itself
        dialog.wait_for(state="detached")  # and the dialog over the item's page closed
        self.assertIn(f"items={self.item.display_id}", printed.url)
        self.assertEqual(printed.locator(".label").count(), 1)
        self.assertTrue(printed.evaluate("() => document.fonts.check('12px \"Liberation Sans\"')"))
        family = printed.evaluate("() => getComputedStyle(document.querySelector('.label .text')).fontFamily")
        self.assertTrue(family.startswith('"Liberation Sans"'))
        # The QR code is drawn as large as the layout says (in the place of the template, grown to its zone).
        expected = next(
            part for part in lay_out(LAYOUTS["small"], labels.layout_texts([self.item])[0]).parts if part.kind == "qr"
        )
        printed.emulate_media(media="print")  # on the screen the labels are shown twice as large
        height = printed.evaluate("() => document.querySelector('.label .qr').getBoundingClientRect().height")
        self.assertAlmostEqual(height / PX_PER_MM, expected.height, delta=0.05)
        printed.close()

    def test_the_labels_of_a_model(self) -> None:
        model = self.item.material_model
        self.open(f"/material/models/{model.pk}/")
        self.page.locator(".page-head .actions").get_by_role("link", name="Etiketten").click()
        self.page.wait_for_url(f"**/material/labels/?model={model.pk}")
        self.assertIn(self.item.display_id, self.page.input_value("#id_items"))
