# SPDX-License-Identifier: GPL-3.0-or-later
"""The three labels of MAT-056 – legible, the QR code as large as the printer allows (MAT-065), chosen in a
click (MAT-066).

* Legibility and cut-off: the labels are as legible as the originals and the cable label is not cut off – they are set
  in Liberation Sans (Arial's metrics, as the P-touch templates) in pure black, everything lies inside the area the
  Brother QL prints, and the text around the cable is repeated as typed.
* The requirement: the QR code uses as much of the available space as possible, respecting the print margins – it is as high as the printable area (on the cable label as wide as the tape prints), each
  module whole printer dots, with a quiet zone of two modules inside the area and two more to the texts.
* The requirement: the labels button of the items is also on the models, and the item view offers only a small dialog
  to choose the label and then shows the label directly – "Etiketten" on the model's page leads to the page of the labels with all its items; "Etikett"
  on an item's page opens a small dialog, and a choice opens the print page of exactly that item and label.
"""

from __future__ import annotations

import base64
import io
import itertools
import re
import tempfile

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.views import serve
from django.core.files.base import ContentFile
from django.templatetags.static import static
from django.test import RequestFactory
from django.urls import reverse
from PIL import Image

from rentalars.material import label_layouts, labels
from rentalars.material.label_layouts import (
    DOT_PT,
    LAYOUTS,
    LEAD_IN_PT,
    MM_PER_PT,
    LabelText,
    lay_out,
    print_logo,
    printable_area,
    text_width,
    wrap_positions,
)
from rentalars.material.models import LabelSettings, MaterialItem
from tests.helpers import RentalarsTestCase, make_item, make_items, make_model
from tests.ui.base import UiTestCase

#: One printer dot in millimetres.
DOT_MM = DOT_PT * MM_PER_PT
#: How far a text's ink reaches above and below the middle of its line, in em (Arial: accents, descenders).
INK_DOWN = 0.57


def logo_png(colour: tuple[int, int, int, int] = (90, 90, 90, 255)) -> bytes:
    """A small square picture with a grey ring – something to make black and white."""
    picture = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    for x in range(120):
        for y in range(120):
            if 40 <= ((x - 60) ** 2 + (y - 60) ** 2) ** 0.5 <= 52:
                picture.putpixel((x, y), colour)
    output = io.BytesIO()
    picture.save(output, format="PNG")
    return output.getvalue()


def customer_text(display_id: str = "1651", **values: object) -> LabelText:
    """What the customer's labels say (his scan)."""
    text = LabelText(
        name="Max Muster - BSP",
        phone_line="Telefonnummer: 01000/5550123",
        id_caption="Equipment-ID:",
        display_id=display_id,
        url="BSP.TEST",
        notice="Hast du Equipment von BSP gefunden? Gebe die nebenstehende ID unter equip.bsp.test ein oder "
        "scanne den QR-Code, danke!",
        wrap_text="EQUIP.BSP.TEST",
        logo=logo_png(),
        qr_content=f"http://equip.bsp.test/id/{display_id}",
        cable_name="Max Muster - BSP",
        phone="01000/5550123",
    )
    for key, value in values.items():
        setattr(text, key, value)
    return text


def area_mm(kind: str, length_mm: float = 90) -> tuple[float, float, float, float]:
    """The printable area in millimetres: left, top, right, bottom."""
    box = printable_area(kind, length_mm)
    return box.x * MM_PER_PT, box.y * MM_PER_PT, box.right * MM_PER_PT, box.bottom * MM_PER_PT


class PrintableAreaTests(RentalarsTestCase):
    """Nothing lies where the driver cuts – the ID of the cable label was cut (MAT-065)."""

    def test_the_areas_of_the_brother_ql(self) -> None:
        # brother_ql label table at 300 dpi: 17 × 54 prints 566 × 165 dots, 29 × 90 991 × 306, the roll 306 across.
        left, top, right, bottom = area_mm("small")
        self.assertAlmostEqual(right - left, 566 * DOT_MM, places=3)
        self.assertAlmostEqual(bottom - top, 165 * DOT_MM, places=3)
        self.assertAlmostEqual(left, 35 * DOT_MM, places=3)
        left, top, right, bottom = area_mm("large")
        self.assertAlmostEqual(right - left, 991 * DOT_MM, places=3)
        self.assertAlmostEqual(bottom - top, 306 * DOT_MM, places=3)
        left, top, right, bottom = area_mm("cable", 90)
        self.assertAlmostEqual(right - left, 306 * DOT_MM, places=3)
        self.assertAlmostEqual(top, 35 * DOT_MM, places=3)
        self.assertAlmostEqual(90 - bottom, 35 * DOT_MM, places=3)

    def test_every_part_lies_inside(self) -> None:
        cases = [("small", 90), ("large", 90), ("cable", 60), ("cable", 90), ("cable", 200)]
        texts = [customer_text(), customer_text("12345", name="XYZ", cable_name="ÄÖÜ Verleih", notice="")]
        for (kind, length), text in ((case, text) for case in cases for text in texts):
            label = lay_out(LAYOUTS[kind], text, length_mm=length)
            left, top, right, bottom = area_mm(kind, length)
            self.assertEqual(label.printable.left, left)
            for part in label.parts:
                where = f"{kind} {length} mm, {part.kind} {part.text or part.lines[:1]}"
                self.assertGreaterEqual(part.left, left - 1e-6, where)
                self.assertGreaterEqual(part.top, top - 1e-6, where)
                self.assertLessEqual(part.left + part.width, right + 1e-6, where)
                self.assertLessEqual(part.top + part.height, bottom + 1e-6, where)
                if part.kind in ("text", "pair"):
                    # The ink of a line: fitted to the width of its box, and above and below its middle inside the area.
                    middle, em = part.top + part.height / 2, part.size * MM_PER_PT
                    # The title hangs at the baseline of the template, so the ink above it is measured from the
                    # baseline (capitals; with accents higher) instead of the 0.5 em above the middle.
                    rise = label_layouts.ink_rise(part.text) - label_layouts.BASELINE_BELOW_MIDDLE
                    self.assertGreaterEqual(middle - rise * em, top - 1e-6, where)
                    self.assertLessEqual(middle + INK_DOWN * em, bottom, where)
                    width = text_width(f"{part.text}  {part.right}" if part.kind == "pair" else part.text, part.size)
                    self.assertLessEqual(width * MM_PER_PT, part.width - 2 * 0.6 * MM_PER_PT + 1e-6, where)
                if part.kind == "lines":
                    self.assertLessEqual(len(part.lines) * part.size * 1.15 * MM_PER_PT, part.height + 1e-6, where)

    def test_the_cable_label_keeps_off_its_ends(self) -> None:
        """The scan: printed from the browser, the roll label came out about 2 mm further to its end."""
        label = lay_out(LAYOUTS["cable"], customer_text(), length_mm=90)
        _left, top, _right, bottom = area_mm("cable")
        self.assertGreaterEqual(min(part.top for part in label.parts) - top, 2.1)
        self.assertGreaterEqual(bottom - max(part.top + part.height for part in label.parts), 2.1)


# Labels like the originals: QrCodeTests – the QR code as high as the printable area, in whole dots
# with a quiet zone of two modules in its drawing – is replaced by tests/unit/test_095_labels.py: the QR code stands in
# the place of the template and grows to the free space of that place.


class TypeTests(RentalarsTestCase):
    """Font, sizes and weights as in the .lbx files; pure black; the logo black and white (MAT-065)."""

    def test_the_font_has_arials_metrics(self) -> None:
        from fontTools.ttLib import TTFont

        path = finders.find(label_layouts.FONT_FILE)
        self.assertTrue(path)
        font = TTFont(path)
        self.assertEqual(font["name"].getDebugName(1), "Liberation Sans")
        self.assertEqual(font["OS/2"].usWeightClass, 400)
        # Arial's advance widths (units of 2048): "T" 1251, "e" 1139, "1" 1139, " " 569.
        self.assertAlmostEqual(text_width("Te1 ", 2048), 1251 + 1139 + 1139 + 569, places=6)

    def test_the_sizes_of_the_templates(self) -> None:
        short = customer_text("0042", name="XYZ", cable_name="XYZ", phone_line="Tel. 0157", notice="")
        sizes = {}
        for kind in ("small", "large", "cable"):
            label = lay_out(LAYOUTS[kind], short, length_mm=90)
            sizes[kind] = sorted({part.size for part in label.parts if part.kind in ("text", "pair")})
        self.assertEqual(sizes["small"], [6, 11])
        self.assertEqual(sizes["large"], [12, 24])
        # The cable label as in the template (phone number 8 points, shrunk into its column as P-touch does).
        # The column of texts starts 12 printer dots further in (SIDE_SAFETY_DOTS), the phone number shrinks to 6.51.
        self.assertEqual(sizes["cable"], [6.51, 7, 8, 12])

    def test_the_text_around_the_cable_as_typed(self) -> None:
        # The rows of the lower end are shorter (QR code beside them), so one repeat more fits in 90 mm.
        for wrap, length, count in (("EQUIP.BSP.TEST", 90, 5), ("equip.bsp.test", 90, 5), ("EQUIP", 200, 13)):
            label = lay_out(LAYOUTS["cable"], customer_text(wrap_text=wrap), length_mm=length)
            repeats = [part for part in label.parts if part.text == wrap]
            self.assertEqual(len(repeats), count, (wrap, length))
            steps = [later.top - earlier.top for earlier, later in itertools.pairwise(repeats)]
            self.assertLessEqual(max(steps), 39.8 * MM_PER_PT + 1e-6)  # at most 14 mm apart, as in the template
            self.assertEqual({part.size for part in repeats}, {8})
        self.assertEqual(wrap_positions(0, 5, 9.6), [])
        self.assertEqual(wrap_positions(10, 30, 9.6), [10])

    def test_the_blank_start_of_the_cable_label(self) -> None:
        """As in the .lbx: the first 18.3 mm of the tape stay blank – the first wrap, covered later."""
        lead_in = LEAD_IN_PT * MM_PER_PT
        self.assertAlmostEqual(lead_in, 18.34, places=2)
        for length in (90, 200):
            label = lay_out(LAYOUTS["cable"], customer_text(), length_mm=length)
            self.assertAlmostEqual(label.lead_in_mm, lead_in, places=6)
            self.assertFalse(label.lead_in_shortened)
            self.assertAlmostEqual(min(part.top for part in label.parts), lead_in, places=6, msg=length)
            first = min((part for part in label.parts if part.text == "EQUIP.BSP.TEST"), key=lambda part: part.top)
            self.assertAlmostEqual(first.top, lead_in, places=6)
        # The lower end of the cable label is shorter (QR code beside the texts, as in the template), so only a
        # label of 40 mm – below the 60 mm the settings allow – is too short for 18 mm, one repeat and the rows: the
        # blank start gives way, nothing else.
        short = lay_out(LAYOUTS["cable"], customer_text(), length_mm=40)
        self.assertTrue(short.lead_in_shortened)
        self.assertLess(short.lead_in_mm, lead_in)
        self.assertGreaterEqual(short.lead_in_mm, area_mm("cable", 40)[1])
        self.assertEqual(len([part for part in short.parts if part.text == "EQUIP.BSP.TEST"]), 1)
        full = next(
            part for part in lay_out(LAYOUTS["cable"], customer_text(), length_mm=90).parts if part.kind == "qr"
        )
        qr = next(part for part in short.parts if part.kind == "qr")
        self.assertAlmostEqual(qr.width, full.width, places=6)  # the QR code keeps its full size

    def test_the_logo_in_black_and_white(self) -> None:
        url, width, height = print_logo(logo_png(), 58, 58)
        self.assertEqual((width, height), (58, 58))
        picture = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("L")
        levels = [value for value, count in enumerate(picture.histogram()) if count]
        self.assertEqual(levels, [0, 255])  # no grey left for the driver to dither
        wide = Image.new("RGB", (300, 100), (255, 255, 255))
        output = io.BytesIO()
        wide.save(output, format="JPEG")
        self.assertEqual(print_logo(output.getvalue(), 108, 108)[1:], (108, 36))
        self.assertEqual(print_logo(b"no picture", 58, 58), ("", 0, 0))

    def test_the_printed_page(self) -> None:
        item = make_item(make_model("Shure SM58"), 42)
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(self.settings(MEDIA_ROOT=media.name))
        LabelSettings.load().logo.save("logo.png", ContentFile(logo_png()), save=True)
        for kind in ("small", "large", "cable"):
            page = labels.render_labels_html([item], label_format=kind, for_browser=True)
            self.assertIn(f'src: url("{static("fonts/LiberationSans-Regular.ttf")}") format("truetype")', page)
            self.assertIn('font-family: "Liberation Sans", Arial, sans-serif; font-weight: 400; color: #000;', page)
            self.assertIn("font-kerning: none", page)
            self.assertIn("image-rendering: pixelated", page)
            self.assertNotIn("#333", page)
            self.assertIn("data:image/png;base64,", page)
            pdf_page = labels.render_labels_html([item], label_format=kind)
            self.assertIn("file://", pdf_page)
        self.assertTrue(labels.render_labels_pdf([item], label_format="cable").startswith(b"%PDF"))


class FontFileTests(UiTestCase):
    """The font of the labels is shipped and served like every static file (MAT-065)."""

    def test_served(self) -> None:
        address = static("fonts/LiberationSans-Regular.ttf")
        self.assertRegex(address, r"^/static/fonts/LiberationSans-Regular\.ttf\?v=[0-9a-f]{10}$")
        response = serve(RequestFactory().get(address), "fonts/LiberationSans-Regular.ttf", insecure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b"".join(response.streaming_content).startswith(b"\x00\x01\x00\x00"))  # TrueType
        self.assertTrue(finders.find("fonts/LiberationSans-OFL.txt"))


class ModelButtonTests(UiTestCase):
    """ "Etiketten" on the model's page: the page of the labels with all its items chosen (MAT-066)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Cordial CPM 5 FM")
        self.items = make_items(self.model, 4)  # 0001-0004
        MaterialItem.objects.filter(pk=self.items[2].pk).update(status="retired")

    def test_the_button_and_the_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        address = f"{reverse('material:labels')}?model={self.model.pk}"
        self.assertRegex(page, re.escape(f'href="{address}"') + r">.*Etiketten</a>")
        labels_page = self.assert_ok(self.client.get(address))
        self.assertIn("0001-0002, 0004</textarea>", labels_page)  # the retired 0003 is left out
        self.assertIn("3 Etiketten", labels_page)
        self.assertIn('value="small" selected', labels_page)  # the label suggested under Einstellungen → Etiketten
        self.assertNotIn("zwingend erforderlich", labels_page)
        # Readers of material see it too; a model without items has none.
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertIn(address, self.assert_ok(reader.get(reverse("material:model_detail", args=[self.model.pk]))))
        empty = make_model("Leer")
        empty_page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[empty.pk])))
        actions = empty_page.split('<div class="actions">', 1)[1].split("</div>", 1)[0]
        self.assertIn("Modell bearbeiten", actions)
        self.assertNotIn(f"{reverse('material:labels')}?model=", actions)

    def test_ids_alone_show_the_choice(self) -> None:
        """Changed: a link naming only IDs (the item list's "Etiketten") shows them, not "required"."""
        page = self.assert_ok(self.client.get(reverse("material:labels"), {"items": "0001,0002"}))
        self.assertIn("2 Etiketten", page)
        self.assertNotIn("zwingend erforderlich", page)


class ItemDialogTests(UiTestCase):
    """ "Etikett" on an item's page: a small dialog; the choice opens the print page of exactly this item (MAT-066)."""

    def setUp(self) -> None:
        super().setUp()
        self.item = make_item(make_model("Shure SM58"), 42)
        make_item(self.item.material_model, 43)
        row = LabelSettings.load()
        row.default_kind = "large"
        row.save()

    def test_the_button_opens_a_dialog(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.item.pk])))
        dialog = reverse("material:item_labels", args=[self.item.pk])
        self.assertIn(f'href="{dialog}" hx-get="{dialog}" hx-target="#dialog" aria-haspopup="dialog"', page)
        part = self.assert_ok(self.htmx("get", dialog))
        self.assertNotIn("<html", part)
        self.assertIn("Etikett für 0042", part)
        kinds = re.findall(r'data-label-kind="([\w-]+)"', part)
        self.assertEqual(kinds, ["large", "small", "cable", "a4-24", "a4-65", "roll-62x29"])  # the suggested first
        self.assertIn("Groß, 29 × 90 mm", part)
        self.assertIn("Kabel, 29-mm-Rolle", part)
        self.assertIn("Bögen und Rolle", part)
        print_url = f"{reverse('material:labels_print')}?items=0042&amp;label_format=small"
        self.assertIn(
            f'href="{print_url}" target="_blank" rel="noopener" data-label-kind="small" data-close-dialog', part
        )
        self.assertIn(f'href="{reverse("material:labels")}?items=0042"', part)  # "Weitere Einstellungen"

    def test_the_choice_prints_this_label_at_once(self) -> None:
        for kind, size in (("small", "54mm 17mm"), ("large", "90mm 29mm"), ("cable", "29mm 90mm")):
            response = self.client.get(reverse("material:labels_print"), {"items": "0042", "label_format": kind})
            page = self.assert_ok(response)
            self.assertIn("data-print-on-load", page)
            self.assertIn(f"@page {{ size: {size}; margin: 0; }}", page)
            self.assertIn("0042", page)
            self.assertNotIn("0043", page)
            self.assertEqual(page.count('<div class="label">'), 1)
        sheet = self.assert_ok(
            self.client.get(reverse("material:labels_print"), {"items": "0042", "label_format": "a4-24"})
        )
        self.assertIn("data-print-on-load", sheet)

    def test_without_javascript_a_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:item_labels", args=[self.item.pk])))
        self.assertIn("<h1>Etiketten</h1>", page)
        self.assertIn("Zurück zum Exemplar", page)
        self.assertNotIn("data-close-dialog", page.split("<main", 1)[1].split("</main>", 1)[0])

    def test_archived_and_rights(self) -> None:
        MaterialItem.objects.filter(pk=self.item.pk).update(status="sold")
        part = self.assert_ok(self.htmx("get", reverse("material:item_labels", args=[self.item.pk])))
        self.assertIn("Archivierte Exemplare bekommen kein Etikett.", part)
        self.assertNotIn("data-label-kind", part)
        crew = self.browser_for("kai", "Crew")
        self.assertEqual(crew.get(reverse("material:item_labels", args=[self.item.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("material:item_labels", args=[999999])).status_code, 404)


class SettingsPreviewTests(UiTestCase):
    """Einstellungen → Etiketten: the preview is the printed label, with the printable area marked (MAT-065)."""

    def test_the_preview(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:label_settings")))
        self.assertEqual(page.count('class="printable-area"'), 3)
        self.assertIn("Die gestrichelte Linie zeigt, was der Etikettendrucker bedrucken kann", page)
        self.assertEqual(page.count('<div class="part qr"'), 3)
        self.assertIn("Freier Anfang (die erste Wicklung, von den folgenden verdeckt): 18 mm.", page)
        self.assertNotIn("Gekürzt", page)
        row = LabelSettings.load()
        # The lower end of the cable label got shorter, so the blank start only gives way below 44 mm (the
        # settings allow 60 mm at least; the page still shows it for a value saved some other way).
        row.cable_length_mm = 40
        row.save()
        page = self.assert_ok(self.client.get(reverse("material:label_settings")))
        self.assertIn("verdeckt): 16 mm. Gekürzt – das Etikett ist zu kurz für die 18 mm der Vorlage", page)
