# SPDX-License-Identifier: GPL-3.0-or-later
"""Labels like the originals: the three labels follow the P-touch templates, the QR code takes their place.

The requirement: the label design follows the original labels, but the QR code takes the same space as on the originals (larger if Rentalars can make it smaller); the order of the name and the abbreviation on the label follows the originals.

* The title prints as typed (Einstellungen → Etiketten, "name on labels", else the company's name) – the order of the
  two parts is the user's, nothing is reordered, and the casing of the web address and the text around the cable too.
* The QR code stands in the place of the template, grown to the free space of that place: never smaller than the
  template's, and the title above it is as wide as the label again.
* Nothing lies outside the printable area, the ID is never cut, on all three labels (small, large, cable).
"""

from __future__ import annotations

import re

from weasyprint import HTML

from rentalars.core.models import CompanyProfile
from rentalars.material import label_layouts, labels
from rentalars.material.label_layouts import (
    BASELINE_BELOW_MIDDLE,
    DOT_PT,
    LAYOUTS,
    MM_PER_PT,
    PADDING_PT,
    QR_BOTTOM_MARGIN,
    QR_GAP,
    Box,
    ink_rise,
    lay_out,
    qr_drawing,
    qr_part,
    text_width,
    usable_area,
)
from rentalars.material.models import LabelSettings
from tests.helpers import RentalarsTestCase, make_item, make_model
from tests.unit.test_091_labels import customer_text

#: The cells of the templates' QR codes in points (qrcodeStyle cellSize: 0.8 small and cable, 1.6 large).
TEMPLATE_CELL = {"small": 0.8, "large": 1.6, "cable": 0.8}
#: The URLs of the labels: short (version 1), as the customer's (version 3), and a long one (version 6).
CONTENTS = ["0042", "http://equip.bsp.test/id/1651", "https://equip.example.de/labels/" + "x" * 70 + "/12345678"]


def part_of(label: label_layouts.LaidOutLabel, kind: str) -> label_layouts.Part:
    """The only part of a kind on a laid out label."""
    (found,) = [part for part in label.parts if part.kind == kind]
    return found


def points(millimetres: float) -> float:
    """Millimetres in points."""
    return millimetres / MM_PER_PT


class TitleTests(RentalarsTestCase):
    """The title and the other texts print as typed (title order of the originals; MAT-085)."""

    def test_the_title_is_what_is_typed(self) -> None:
        item = make_item(make_model("Shure SM58"), 1651)
        row = LabelSettings.load()
        row.company_name = "BSP - Max Muster"
        row.url = "BSP.TEST"
        row.wrap_text = "equip.bsp.test"
        row.save()
        text = labels.layout_texts([item])[0]
        self.assertEqual(text.name, "BSP - Max Muster")  # company first, then the name – as the originals
        self.assertEqual((text.url, text.wrap_text), ("BSP.TEST", "equip.bsp.test"))  # the casing as typed
        for kind, length in (("small", 90), ("large", 90), ("cable", 90)):
            label = lay_out(LAYOUTS[kind], text, length_mm=length)
            printed = [part.text for part in label.parts if part.kind == "text"]
            if kind != "cable":
                self.assertIn("BSP - Max Muster", printed, kind)
            self.assertIn("BSP.TEST", printed)

    def test_the_other_order_when_typed_so(self) -> None:
        """No order is built into the code: the name of the company is printed as it is stored."""
        company = CompanyProfile.load()
        company.name = "Max Muster - BSP"
        company.save()
        row = LabelSettings.load()
        row.company_name = ""
        row.save()
        self.assertEqual(labels.layout_texts([make_item(make_model("Shure SM58"), 1)])[0].name, "Max Muster - BSP")
        row.company_name = "BSP - Max Muster"
        row.save()
        self.assertEqual(labels.layout_texts([make_item(make_model("Shure SM57"), 2)])[0].name, "BSP - Max Muster")

    def test_the_title_is_as_wide_as_the_label(self) -> None:
        """Squeezed it beside a QR code of the full height (24 points shrunk to 15); now it hangs above the QR code."""
        for kind, size in (("small", 11), ("large", 24)):
            label = lay_out(LAYOUTS[kind], customer_text(name="BSP - Max Muster"))
            title = next(part for part in label.parts if part.text == "BSP - Max Muster")
            qr = part_of(label, "qr")
            self.assertEqual(title.size, size, kind)  # the size of the template, not shrunk
            self.assertGreater(title.left + title.width, qr.left + qr.width - 1e-6, kind)  # reaches over the QR code
            # Its ink (to the lowest descender) ends above the ink of the QR code.
            baseline = title.top + title.height / 2 + BASELINE_BELOW_MIDDLE * title.size * MM_PER_PT
            self.assertLess(baseline + 0.212 * title.size * MM_PER_PT, qr.top, kind)

    def test_the_title_hangs_where_p_touch_sets_it(self) -> None:
        """The text starts at the top of the template's box: the baseline lies 0.905 em below it (± the 0.3 points)."""
        for kind, top, size in (("small", 2.3, 11), ("large", 0.4, 24)):
            title = next(
                part
                for part in lay_out(LAYOUTS[kind], customer_text(name="BSP - Max Muster")).parts
                if part.text == "BSP - Max Muster"
            )
            baseline = points(title.top + title.height / 2 + BASELINE_BELOW_MIDDLE * title.size * MM_PER_PT)
            self.assertAlmostEqual(baseline, top + 0.905 * size, delta=0.5, msg=kind)


class QrPlaceTests(RentalarsTestCase):
    """The QR code takes the place of the template and grows to its free space – never smaller."""

    def test_never_smaller_than_the_template(self) -> None:
        for content in CONTENTS:
            modules = qr_drawing(content).modules
            for kind in ("small", "large", "cable"):
                label = lay_out(LAYOUTS[kind], customer_text(qr_content=content), length_mm=90)
                qr = part_of(label, "qr")
                side = points(qr.width)
                self.assertAlmostEqual(qr.width, qr.height, places=6)
                # P-touch draws the same code at its cell size: the QR code is at least that large (0.5 % for the rounding) …
                if modules * TEMPLATE_CELL[kind] <= LAYOUTS[kind].qr.w:  # a longer code P-touch shrinks into its box
                    self.assertGreaterEqual(side, modules * TEMPLATE_CELL[kind] * 0.995, (kind, content))
                # … and fills the box of the template (a few per cent less where the quiet zone takes its modules).
                self.assertGreaterEqual(side, 0.95 * LAYOUTS[kind].qr.w, (kind, content))

    def test_the_share_of_the_label_as_on_the_originals(self) -> None:
        """The scan of the originals: the QR code is about half the height of the small label, 0.55 of the large."""
        small = part_of(lay_out(LAYOUTS["small"], customer_text()), "qr")
        large = part_of(lay_out(LAYOUTS["large"], customer_text()), "qr")
        cable = part_of(lay_out(LAYOUTS["cable"], customer_text(), length_mm=90), "qr")
        self.assertGreaterEqual(small.height / 17, 0.49)
        self.assertGreaterEqual(large.height / 29, 0.55)
        self.assertGreaterEqual(cable.height, 8.1)  # millimetres: 23.2 points as on the template
        # The customer's version 3 code, 29 modules: larger than the template's 0.8 and 1.6 points per module.
        self.assertGreater(points(small.width), 29 * 0.8)
        self.assertGreater(points(large.width), 29 * 1.6)

    def test_it_stands_at_the_places_of_the_template(self) -> None:
        # Small: at the right end, below the title; large: right and below the title; cable: lower left, as templates.
        for kind in ("small", "large"):
            label = lay_out(LAYOUTS[kind], customer_text())
            qr, area = part_of(label, "qr"), usable_area(kind)
            template = LAYOUTS[kind].qr
            self.assertGreaterEqual(points(qr.left), template.x - 3.0, kind)
            self.assertAlmostEqual(points(qr.left + qr.width), area.right, places=3, msg=kind)  # to the end of the area
            self.assertGreaterEqual(points(qr.top), template.y - 1e-6, kind)
            # one module of quiet zone to the lower end of the area
            module = qr.width / qr_drawing(customer_text().qr_content).modules
            self.assertAlmostEqual(
                points(qr.top + qr.height + QR_BOTTOM_MARGIN * module), area.bottom, places=2, msg=kind
            )
        label = lay_out(LAYOUTS["cable"], customer_text(), length_mm=90)
        qr, area = part_of(label, "qr"), usable_area("cable", 90)
        self.assertAlmostEqual(points(qr.left), area.x, places=3)  # lower left
        self.assertLess(
            points(qr.left + qr.width), LAYOUTS["cable"].name.box.x + label_layouts.SIDE_SAFETY_DOTS["cable"] * DOT_PT
        )  # left of the column of texts
        self.assertAlmostEqual(points(qr.top + qr.height), area.bottom - 0.8, delta=0.1)

    def test_the_cable_qr_code_keeps_off_the_left_edge_of_the_printable_area(self) -> None:
        """In the customer's scan the leftmost modules were missing – the printer printed about 9 dots less."""
        side = label_layouts.printable_area("cable", 90).x  # the 18 dots of the label table
        for content in CONTENTS:
            label = lay_out(LAYOUTS["cable"], customer_text(qr_content=content), length_mm=90)
            qr, logo = part_of(label, "qr"), part_of(label, "logo")
            self.assertGreaterEqual(
                points(qr.left) - side, 12 * DOT_PT - 1e-6, content
            )  # at least 12 dots further in (SIDE_SAFETY_DOTS)
            self.assertGreaterEqual(points(logo.left), side, content)
            # the modules stay legible: at least 1.8 printer dots each
            self.assertGreaterEqual(qr.width / qr_drawing(content).modules / MM_PER_PT / DOT_PT, 1.8, content)
        # the other labels are not moved
        self.assertEqual(label_layouts.SIDE_SAFETY_DOTS["small"] + label_layouts.SIDE_SAFETY_DOTS["large"], 0)

    def test_texts_keep_two_modules_off(self) -> None:
        for content in CONTENTS:
            for kind in ("small", "large"):
                label = lay_out(LAYOUTS[kind], customer_text(qr_content=content))
                qr = part_of(label, "qr")
                gap = QR_GAP * qr.width / qr_drawing(content).modules
                for part in label.parts:
                    beside = part.top < qr.top + qr.height and part.top + part.height > qr.top
                    if part.kind in ("text", "lines") and beside:
                        # a text at the height of the QR code ends two modules before it (the title is above it)
                        if part.top + part.height / 2 > qr.top:
                            self.assertLessEqual(part.left + part.width, qr.left - gap + 1e-6, (kind, part.text))

    def test_whole_dots_where_it_costs_little_else_fractions(self) -> None:
        # 29 modules in 209 dots (+1 of quiet zone): 6.97 dots each – whole dots (6) would cost 14 %: fractions.
        zone = Box(0, 0, 209 * DOT_PT, 214 * DOT_PT)
        part, _keep = qr_part("http://equip.bsp.test/id/1651", zone, bottom=1)
        self.assertGreater(part.width, 29 * 6.5 * DOT_PT * MM_PER_PT)
        # 29 modules in 88 dots: 3.03 dots each – whole dots (3) cost only 1 %: whole.
        part, _keep = qr_part("http://equip.bsp.test/id/1651", Box(0, 0, 88 * DOT_PT, 88 * DOT_PT))
        self.assertAlmostEqual(part.width / MM_PER_PT / DOT_PT, 29 * 3.0, places=6)
        # The keep-free rectangle: two modules to the left and above.
        part, keep = qr_part("0042", Box(10, 10, 100, 100))
        module = part.width / MM_PER_PT / 21
        self.assertAlmostEqual(points(part.left) - keep.x, QR_GAP * module, places=6)
        self.assertAlmostEqual(points(part.top) - keep.y, QR_GAP * module, places=6)

    def test_the_drawing_has_no_border(self) -> None:
        drawing = qr_drawing("http://equip.bsp.test/id/1651")
        self.assertEqual(drawing.modules, 29)
        self.assertIn('viewBox="0 0 29 29"', drawing.svg)
        self.assertIn('shape-rendering="crispEdges"', drawing.svg)
        rows = {int(row) for _x, row in re.findall(r"M(\d+) (\d+)h", drawing.svg)}
        self.assertEqual((min(rows), max(rows)), (0, 28))  # the finder patterns touch the edges of the drawing


class InsideTheAreaTests(RentalarsTestCase):
    """Nothing lies outside what the printer prints, nothing is cut – on all three labels (MAT-065)."""

    TEXTS = (
        {},
        {"display_id": "12345678"},  # eight digits
        {"display_id": "12345678", "name": "Ärztehaus Müller & Söhne Veranstaltungstechnik GmbH", "notice": ""},
        {
            "name": "Überlänge " * 8,
            "cable_name": "Ärger " * 8,
            "phone_line": "Telefonnummer: +49 (0) 100 / 5550123-12",
        },
        {"name": "", "logo": b""},  # no title and no logo
    )

    def test_every_part_lies_inside_and_fits(self) -> None:
        for values in self.TEXTS:
            for kind, length in (("small", 90), ("large", 90), ("cable", 60), ("cable", 90), ("cable", 200)):
                text = customer_text(**values)
                label = lay_out(LAYOUTS[kind], text, length_mm=length)
                area = label_layouts.printable_area(kind, length)
                left, top, right, bottom = area.x, area.y, area.right, area.bottom
                for part in label.parts:
                    where = f"{kind} {length} mm {values} {part.kind} {part.text or part.lines[:1]}"
                    self.assertGreaterEqual(points(part.left), left - 1e-6, where)
                    self.assertGreaterEqual(points(part.top), top - 1e-6, where)
                    self.assertLessEqual(points(part.left + part.width), right + 1e-6, where)
                    self.assertLessEqual(points(part.top + part.height), bottom + 1e-6, where)
                    if part.kind in ("text", "pair"):
                        shown = f"{part.text}  {part.right}" if part.kind == "pair" else part.text
                        self.assertLessEqual(
                            text_width(shown, part.size), points(part.width) - 2 * PADDING_PT + 1e-6, where
                        )
                        middle, em = points(part.top + part.height / 2), part.size
                        self.assertGreaterEqual(
                            middle - (ink_rise(part.text) - BASELINE_BELOW_MIDDLE) * em, top - 1e-6, where
                        )
                        self.assertLessEqual(middle + 0.57 * em, bottom + 1e-6, where)
                    if part.kind == "lines":
                        self.assertLessEqual(len(part.lines) * part.size * 1.15, points(part.height) + 1e-6, where)

    def test_the_id_is_never_cut(self) -> None:
        for display_id in ("1", "1651", "12345678", "ABC-12345678"):
            text = customer_text(display_id)
            for kind in ("small", "large"):
                label = lay_out(LAYOUTS[kind], text)
                ident = next(part for part in label.parts if part.text.endswith(display_id))
                self.assertLessEqual(
                    text_width(ident.text, ident.size), points(ident.width) - 2 * PADDING_PT + 1e-6, (kind, display_id)
                )
                self.assertGreaterEqual(ident.size, 4.0, (kind, display_id))  # shrunk a little, still legible
            cable = lay_out(LAYOUTS["cable"], text, length_mm=90)
            pair = next(part for part in cable.parts if part.kind == "pair")
            self.assertEqual(pair.right, display_id)
            self.assertLessEqual(
                text_width(f"{pair.text}  {pair.right}", pair.size), points(pair.width) - 2 * PADDING_PT + 1e-6
            )
            self.assertGreaterEqual(pair.size, 4.0)

    def test_the_cable_label_as_the_template(self) -> None:
        """QR code and logo at the left, name, web address, phone number and ID in a column beside them."""
        label = lay_out(LAYOUTS["cable"], customer_text(), length_mm=90)
        qr, area = part_of(label, "qr"), usable_area("cable", 90)
        logo = part_of(label, "logo")
        column = LAYOUTS["cable"].name.box.x
        self.assertLessEqual(points(logo.left + logo.width), column)  # the logo is in the left part as well
        self.assertLessEqual(points(logo.top + logo.height), points(qr.top))  # above the QR code
        texts = [part for part in label.parts if part.kind in ("text", "pair") and part.text not in ("EQUIP.BSP.TEST",)]
        for part in texts:
            self.assertGreaterEqual(points(part.left), column - 1e-6, part.text)
        order = [part.text for part in sorted(texts, key=lambda part: part.top)]
        self.assertEqual(order, ["Max Muster - BSP", "BSP.TEST", "01000/5550123", "ID:"])
        # The rows end at the lower end of the area, as the template's end at its printable end.
        self.assertAlmostEqual(points(max(part.top + part.height for part in label.parts)), area.bottom, places=3)

    def test_the_wrap_text_keeps_off_the_rows(self) -> None:
        label = lay_out(LAYOUTS["cable"], customer_text(), length_mm=200)
        repeats = [part for part in label.parts if part.text == "EQUIP.BSP.TEST"]
        top_of_rows = min(
            part.top for part in label.parts if part.kind in ("logo", "qr") or part.text == "Max Muster - BSP"
        )
        self.assertTrue(repeats)
        self.assertLess(max(part.top + part.height for part in repeats), top_of_rows)


class PdfTests(RentalarsTestCase):
    """The labels come out as PDF, one label per page in its size (smoke test)."""

    def test_a_pdf_for_each_kind(self) -> None:
        item = make_item(make_model("Shure SM58"), 1651)
        row = LabelSettings.load()
        row.company_name = "BSP - Max Muster"
        row.phone = "01000/5550123"
        row.url = "BSP.TEST"
        row.notice = "Hast du Equipment von BSP gefunden? Gebe die nebenstehende ID unter equip.bsp.test ein."
        row.save()
        for kind, size in (("small", (54, 17)), ("large", (90, 29)), ("cable", (29, row.cable_length_mm))):
            self.assertTrue(labels.render_labels_pdf([item], label_format=kind).startswith(b"%PDF"), kind)
            document = HTML(string=labels.render_labels_html([item], label_format=kind)).render()
            self.assertEqual(len(document.pages), 1, kind)
            page = document.pages[0]
            self.assertAlmostEqual(page.width / 96 * 25.4, size[0], delta=0.01, msg=kind)
            self.assertAlmostEqual(page.height / 96 * 25.4, size[1], delta=0.01, msg=kind)
        html = labels.render_labels_html([item], label_format="large")
        self.assertIn("BSP - Max Muster", html)
        self.assertIn('class="part qr"', html)
