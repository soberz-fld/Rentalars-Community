# SPDX-License-Identifier: GPL-3.0-or-later
"""The three labels of MAT-056, laid out like the operator's P-touch templates (MAT-065).

The templates ``FLD_Etiketten_v2-17x54.lbx``, ``FLD_Etiketten_v2-29x90.lbx``
and ``FLD_EtikettenKabel_v2.1-29.lbx`` place every element in points
(1/72 inch) on the label, set in Arial (regular, weight 400). The sizes below
are theirs, the places too as far as the larger QR code and the printable
area allow; only what is printed comes from Einstellungen →
Etiketten (:class:`LabelSettings`):

Small, 17 × 54 mm, and large, 29 × 90 mm (the same layout, scaled)::

    ┌───────────────────────────────────────────────┐
    │ [Logo]    Company - Name (title)              │
    │ Telefonnummer: 01577 …                ┌─────┐ │
    │ Equipment-ID: 0427  Text for          │ QR  │ │
    │      EXAMPLE.DE     finders …         │     │ │
    │                                       └─────┘ │
    └───────────────────────────────────────────────┘

Cable, 29 mm roll, 90 mm long (portrait): a blank start of 18 mm (the first
wrap around the cable, covered by the next ones), then the part that wraps
around the cable and repeats a text across the tape (``wrap_text``); the lower
end is laid out as in the template: the logo above the QR code on the left,
beside them name, web address, phone number and ID in a column. A longer label
repeats the text more often (``LabelSettings.cable_length_mm``); a label too
short for all of it gets a shorter blank start (:data:`LEAD_IN_PT`).

MAT-065 (labels: legible, nothing cut off):

* **The printable area.** A Brother QL printer cannot print the outermost
  dots of a label: 35 dots (3 mm) at each end of the feed and 18 dots
  (1.5 mm) at each side, at 300 dpi – the driver cuts away what lies there
  (the label table of the brother_ql project: 17 × 54 mm prints 165 × 566 of
  201 × 636 dots, 29 × 90 mm 306 × 991 of 342 × 1061, the 29 mm roll 306
  dots across). Every part lies inside this area (:func:`printable_area`),
  and a little further in at the ends of the feed (:data:`FEED_SAFETY_DOTS`,
  :func:`usable_area`): printed from the browser, the customer's labels came
  out shifted along the feed, and the ID of the cable label was cut.
* **The font** is Liberation Sans (SIL OFL 1.1, ``static/fonts``): metrically
  the same as Arial, the font of the templates, and as heavy. Barlow, the font
  of the interface, printed thin and grey on the thermal printer.
* **The logo** is turned into pure black and white at the printer's
  resolution, as P-touch does (threshold 128) – the printer's driver would
  dither the grey of a scaled picture into a faint pattern (:func:`print_logo`).

(labels like the originals; MAT-085): the customer put his labels next to the
originals of the P-touch templates and asked that the design follows them and
that the QR code takes the place it has there – and is scaled up where Rentalars
would make it smaller. So:

* **The layout is the template's** on all three labels: the title as wide as
  the label above the QR code, its baseline where P-touch sets it
  (the text hangs from the top of its box), the text for finders in the box of
  the template, the cable label with the QR code at its lower left and the
  texts beside it.
* **The QR code stands in the place of the template** (:attr:`Layout.qr`,
  the box in which P-touch draws it, with its quiet zone), grown to the free
  space of that place (:func:`qr_zone`: to the end of the printable area on
  the right and at the bottom, on the large label to just below the title)
  and never smaller than P-touch draws it: its modules are as large as the
  place allows, whole printer dots where that costs at most 3 % of the size,
  else fractions of a dot, as P-touch's 0.8 and 1.6 point cells are
  (:func:`qr_part`). The quiet zone is the white around it – a module at the
  bottom, two modules to the texts (the paper beyond the printable area
  completes it).
* **The text of the title is what is typed** in Einstellungen → Etiketten
  ("name on labels", else the name of the company): nothing is reordered,
  "BSP - Max Muster" prints as that. Likewise the casing of every text.

P-touch shrinks a text that does not fit its box. So does :func:`fit_size`,
with the advance widths of the letters of the font – the browser and the PDF
draw them without kerning, so the result is the same in both. A text for
finders is broken into lines here for the same reason.
"""

from __future__ import annotations

import base64
import functools
import io
import math
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from django.contrib.staticfiles import finders
from django.utils.safestring import SafeString, mark_safe

from rentalars.core.pictures import open_picture

#: Millimetres per point.
MM_PER_PT = 25.4 / 72
#: The resolution of the Brother QL printers; one printer dot in points (MAT-065).
PRINT_DPI = 300
DOT_PT = 72 / PRINT_DPI
#: The dots a Brother QL cannot print at each end of the feed and at each side of the tape (brother_ql label table).
FEED_MARGIN_DOTS = 35
SIDE_MARGIN_DOTS = 18
#: Further dots kept free at each end of the feed: printed from the browser, the driver shifted the labels along the
#: feed – in the customer's scan the large label by about 0.6 mm, the cable label by about 2.1 mm, which cut
#: off its ID and a strip of its QR code (MAT-065).
FEED_SAFETY_DOTS = {"small": 7, "large": 7, "cable": 26}
#: Further dots kept free at the left side of the cable label: in the customer's scan of a printed cable label
#: the leftmost modules of the QR code were missing – it began exactly at the edge of the printable area, and the
#: printer (from the browser) printed about 9 dots less there than the label table says. The QR code and the logo of
#: the cable label start this far further in, and the column of texts beside them starts as far further in too (its
#: right end stays where the template has it, the texts shrink to fit a little narrower), so that the QR code keeps the
#: size of the template.
SIDE_SAFETY_DOTS = {"small": 0, "large": 0, "cable": 12}
#: The font of the labels, shipped in ``static/fonts`` (MAT-065): Liberation Sans – Arial's metrics.
FONT_FILE = "fonts/LiberationSans-Regular.ttf"
#: Texts are never printed smaller than this (points); below it a text is cut.
MIN_SIZE_PT = 2.0
#: How far Liberation Sans reaches above the baseline, in em: ascenders and capitals; capitals with an accent (Ä, É …).
INK_RISE = 0.716
INK_RISE_ACCENT = 0.93
#: A line of height 1 em (the CSS of the labels) has its baseline this far below its middle: (ascent 0.905 - descent
#: 0.212) / 2 – the text of a title is placed with it.
BASELINE_BELOW_MIDDLE = 0.3465
#: Line height of the text for finders, as a factor of its size.
LINE_HEIGHT = 1.15
#: Room left free at both ends of a text box (points), as P-touch does.
PADDING_PT = 0.6
#: The gap between the QR code and the texts next to it, in modules (the paper around completes the quiet zone).
QR_GAP = 2
#: Quiet zone kept free below the QR code of the small and large label, in modules: the printer prints 18 dots less
#: at the side, together about the four modules the QR standard asks for.
QR_BOTTOM_MARGIN = 1
#: A QR code takes whole printer dots per module if that costs at most this share of its size; else it is drawn with
#: fractions of a dot, as P-touch draws it with cells of 0.8 and 1.6 points.
QR_WHOLE_DOT_SHARE = 0.97
#: Cable label: the repeated text is at most this far apart (points, 14 mm as in the template).
WRAP_STEP_PT = 39.8
#: Cable label: the blank start of the tape – its first wrap around the cable, covered by the following ones. In
#: FLD_EtikettenKabel_v2.1-29.lbx the first repeat of the text begins 52 points (18.3 mm) after the start.
LEAD_IN_PT = 52.0


@dataclass(frozen=True)
class Box:
    """A place on the label in points: left, top, width, height."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        """Where the box ends on the right."""
        return self.x + self.w

    @property
    def bottom(self) -> float:
        """Where the box ends at the bottom."""
        return self.y + self.h

    def up_to(self, right: float) -> Box:
        """The box ending at ``right`` at the latest (a text beside the QR code)."""
        return Box(self.x, self.y, max(min(self.right, right) - self.x, 1.0), self.h)


@dataclass(frozen=True)
class TextSpec:
    """A text of the template: its box, its size in points and its alignment."""

    box: Box
    size: float
    align: str = "left"


@dataclass(frozen=True)
class Layout:
    """One kind of label: its size in millimetres and where its parts go.

    Every box in points from the upper left corner, as the template has it
    but for the 1.68 points (7 dots) of safety at the ends of the feed
    (:data:`FEED_SAFETY_DOTS`) and the printable area. ``qr`` is the box in
    which P-touch draws the QR code; the QR code grows from it to the free
    space of its place (:func:`qr_zone`). Cable: the boxes of the lower end
    are those of the template for a label 90 mm long; they are moved to the end
    of the label at run time (:func:`_lay_out_cable`).
    """

    kind: str
    width_mm: float
    height_mm: float
    logo: Box
    name: TextSpec
    phone: TextSpec
    ident: TextSpec
    url: TextSpec
    qr: Box
    notice: TextSpec | None = None
    #: Cable label: the text repeated around the cable – its height and size; the step comes from WRAP_STEP_PT.
    wrap: TextSpec | None = None


#: What a Brother QL prints of each label, in dots at 300 dpi (brother_ql label table): along the feed × across the
#: tape; the 29 mm roll prints 306 dots across, along it everything but the 35 dots at each end.
PRINTABLE_DOTS = {"small": (566, 165), "large": (991, 306), "cable": (0, 306)}


def printable_area(kind: str, length_mm: float = 0) -> Box:
    """The part of a label the printer can print, in points from the upper left corner (MAT-065).

    Small and large run through the printer lying (the long side along the
    feed), the cable label standing: its ``length_mm`` runs along the feed.
    """
    feed, side = FEED_MARGIN_DOTS * DOT_PT, SIDE_MARGIN_DOTS * DOT_PT
    along, across = PRINTABLE_DOTS[kind]
    if kind == "cable":
        return Box(side, feed, across * DOT_PT, length_mm / MM_PER_PT - 2 * feed)
    return Box(feed, side, along * DOT_PT, across * DOT_PT)


def usable_area(kind: str, length_mm: float = 0) -> Box:
    """The printable area less :data:`FEED_SAFETY_DOTS` at each end of the feed – where the parts are placed.

    The cable label also keeps:data:`SIDE_SAFETY_DOTS` free at its left side.
    """
    area = printable_area(kind, length_mm)
    safety = FEED_SAFETY_DOTS[kind] * DOT_PT
    if kind == "cable":
        left = SIDE_SAFETY_DOTS[kind] * DOT_PT
        return Box(area.x + left, area.y + safety, area.w - left, area.h - 2 * safety)
    return Box(area.x + safety, area.y, area.w - 2 * safety, area.h)


#: Small label, 17 × 54 mm (Brother DK-11204), from FLD_Etiketten_v2-17x54.lbx; 1.68 points (7 dots) further in from the
#: ends than the template (MAT-065). The title hangs in a box that puts its baseline where P-touch sets it (the text
#: starts at the top of the template's box: 2.3 + 0.905 × 11 = 12.3 points) plus 0.3 points so that its ink lies inside
#: the printable area; the QR code stands where the template draws it (118.4, 18.3; 23.8 points square), the text for
#: finders in its box (76.4, 26.3; 40 × 16.2 points). (labels like the originals; MAT-085)
SMALL = Layout(
    kind="small",
    width_mm=54,
    height_mm=17,
    logo=Box(10.08, 4.4, 13.9, 13.9),
    name=TextSpec(Box(24.08, 4.32, 118.48, 8.94), 11, "center"),
    phone=TextSpec(Box(10.08, 17.4, 132.48, 8.0), 6),
    ident=TextSpec(Box(10.08, 25.4, 65.0, 8.0), 6),
    url=TextSpec(Box(10.08, 33.4, 56.0, 10.0), 6, "center"),
    qr=Box(118.4, 18.3, 23.8, 23.8),
    notice=TextSpec(Box(76.4, 25.0, 40.0, 18.92), 2.8, "justify"),
)

#: Large label, 29 × 90 mm (Brother DK-11201), from FLD_Etiketten_v2-29x90.lbx; 1.68 points (7 dots) further in from the
#: ends than the template (MAT-065). Title: baseline at 0.4 + 0.905 × 24 = 22.1 points plus 0.3. QR code where the
#: template draws it (194.4, 26.4; 47.5 points square) but starting below the title (28.4, the end of its box) and
#: reaching to the end of the printable area; the text for finders beside the ID. (labels like the originals; MAT-085)
LARGE = Layout(
    kind="large",
    width_mm=90,
    height_mm=29,
    logo=Box(10.08, 4.4, 26.0, 26.0),
    name=TextSpec(Box(36.08, 4.32, 208.48, 19.53), 24, "center"),
    phone=TextSpec(Box(10.08, 30.72, 234.48, 14.28), 12),
    ident=TextSpec(Box(10.08, 45.0, 114.0, 15.6), 12),
    url=TextSpec(Box(10.08, 61.0, 114.0, 15.6), 12, "center"),
    qr=Box(194.4, 28.4, 47.5, 47.5),
    notice=TextSpec(Box(124.4, 45.0, 120.16, 32.76), 5.3, "justify"),
)

#: Where the rows of the cable label end in the template: the bottom of the box of the ID (238.5 + 8.9 points).
CABLE_TEMPLATE_BOTTOM = 247.4
#: Cable label, 29 mm roll (Brother DK-22210), 90 mm long, from FLD_EtikettenKabel_v2.1-29.lbx, every box and size as in
#: the template (P-touch shrinks the name and the phone number into their column, :func:`fit_size` does the same):
#: the logo above the QR code at the lower left, the column of name, web address, phone number and ID right of them.
#: Everything but the repeated text moves to the end of the label at run time (:func:`_lay_out_cable`).
#: (labels like the originals; MAT-085)
CABLE = Layout(
    kind="cable",
    width_mm=29,
    height_mm=90,
    logo=Box(8.3, 206.4, 13.9, 13.9),
    name=TextSpec(Box(28.3, 206.4, 49.4, 12.6), 12),
    url=TextSpec(Box(28.3, 219.4, 49.4, 9.6), 7, "right"),
    phone=TextSpec(Box(28.3, 229.4, 49.4, 8.9), 8, "right"),
    ident=TextSpec(Box(28.8, 238.5, 48.9, 8.9), 7, "between"),
    qr=Box(4.7, 222.8, 23.8, 23.8),
    wrap=TextSpec(Box(0, 0, 0, 9.6), 8, "center"),
)

LAYOUTS = {layout.kind: layout for layout in (SMALL, LARGE, CABLE)}


# --- Widths of the letters ------------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _metrics() -> tuple[dict[int, int], int, int]:
    """The advance widths of the label font by character, its units per em and the width of a missing letter."""
    from fontTools.ttLib import TTFont

    font = TTFont(finders.find(FONT_FILE), lazy=True)
    cmap = font.getBestCmap()
    advances = font["hmtx"].metrics
    widths = {code: advances[name][0] for code, name in cmap.items() if name in advances}
    fallback = widths.get(ord("n"), 1139)
    return widths, font["head"].unitsPerEm, fallback


def text_width(text: str, size: float) -> float:
    """How wide a text is in points at a size, set in the label font without kerning."""
    widths, units, fallback = _metrics()
    return sum(widths.get(ord(character), fallback) for character in text) * size / units


def fit_size(text: str, size: float, width: float) -> float:
    """The size at which a text fits a width: the template's size, or smaller (as "shrink" in P-touch)."""
    room = max(width - 2 * PADDING_PT, 1.0)
    natural = text_width(text, size)
    if natural <= room:
        return size
    return max(MIN_SIZE_PT, math.floor(size * room / natural * 100) / 100)


def wrap_lines(text: str, size: float, width: float) -> list[str]:
    """Break a text into lines that fit a width at a size; a word longer than the line gets a line of its own."""
    room = max(width - 2 * PADDING_PT, 1.0)
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and text_width(candidate, size) > room:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return [line for line in lines if line] or []


def fit_block(text: str, size: float, width: float, height: float) -> tuple[float, list[str]]:
    """A text of several lines in a box: the template's size if it fits, else smaller, at least :data:`MIN_SIZE_PT`."""
    current = size
    while True:
        lines = wrap_lines(text, current, width)
        widest = max((text_width(line, current) for line in lines), default=0.0)
        fits = len(lines) * current * LINE_HEIGHT <= height and widest <= max(width - 2 * PADDING_PT, 1.0)
        if fits or current <= MIN_SIZE_PT:
            return current, lines
        current = max(MIN_SIZE_PT, round(current * 0.95, 2))


# --- QR code and logo at the printer's resolution ------------------------------------------------------------


def _dots(points: float) -> int:
    """Whole printer dots in a length of points (rounded down)."""
    return int(points / DOT_PT + 1e-6)


@dataclass(frozen=True)
class QrDrawing:
    """A QR code drawn as SVG: the modules only (no quiet zone) and their number per side."""

    svg: SafeString
    modules: int


def qr_drawing(content: str) -> QrDrawing:
    """The QR code as SVG of ``modules`` × ``modules`` units, black modules only (MAT-065 had a border in it).

    Error correction M ("15 %", as in the templates); segno takes a higher
    level where the size stays the same. Never a Micro QR code – phones do not
    read those. The quiet zone is the white around the drawing (:func:`qr_part`).
    """
    import segno

    code = segno.make_qr(content or " ", error="m")
    modules = code.symbol_size(border=0)[0]
    runs = []
    for row, line in enumerate(code.matrix_iter(border=0)):
        column = 0
        cells = list(line)
        while column < len(cells):
            if cells[column]:
                start = column
                while column < len(cells) and cells[column]:
                    column += 1
                runs.append(f"M{start} {row}h{column - start}v1h-{column - start}z")
            else:
                column += 1
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {modules} {modules}" shape-rendering="crispEdges" '
        f'aria-hidden="true"><path fill="#000" d="{"".join(runs)}"/></svg>'
    )
    return QrDrawing(svg=mark_safe(svg), modules=modules)  # noqa: S308 - numbers only


def read_image(file: Any) -> bytes:
    """The bytes of a stored picture, or ``b""`` if there is none or it cannot be read."""
    if not file:
        return b""
    try:
        with file.open("rb") as handle:
            return handle.read()
    except (OSError, ValueError):
        return b""


@functools.lru_cache(maxsize=6)
def print_logo(data: bytes, width_dots: int, height_dots: int) -> tuple[str, int, int]:
    """The logo in pure black and white at the printer's resolution – a PNG ``data:`` address and its size in dots.

    As P-touch prints a picture (mono, threshold 128): scaled into the box
    keeping its proportions (each dot the average of the picture under it),
    transparent parts white, then every dot darker than the middle black and
    the rest white. Nothing grey is left for the driver to dither. ``("", 0, 0)``
    for a file that is no picture.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        with open_picture(io.BytesIO(data), ["PNG", "JPEG"]) as source:  # what a logo can be
            source.load()
            picture = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return "", 0, 0
    white = Image.new("RGBA", picture.size, (255, 255, 255, 255))
    grey = Image.alpha_composite(white, picture).convert("L")
    scale = min(width_dots / grey.width, height_dots / grey.height)
    size = (max(1, round(grey.width * scale)), max(1, round(grey.height * scale)))
    black_white = grey.resize(size, Image.Resampling.BOX).point(lambda value: 255 if value >= 128 else 0).convert("1")
    output = io.BytesIO()
    black_white.save(output, format="PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(output.getvalue()).decode('ascii')}", size[0], size[1]


# --- One label ----------------------------------------------------------------------------------------------


@dataclass
class Part:
    """One element of a label as the template draws it: positions in millimetres, size in points."""

    kind: str  # "text", "pair", "lines", "logo", "qr"
    left: float
    top: float
    width: float
    height: float
    size: float = 0.0
    align: str = "left"
    text: str = ""
    #: "pair": the text on the right; "lines": the lines of the text.
    right: str = ""
    lines: list[str] = field(default_factory=list)
    #: "qr": the SVG drawing; "logo": the data address of the picture.
    content: Any = ""

    @property
    def style(self) -> str:
        """The position as inline CSS."""
        return f"left:{self.left:.4f}mm;top:{self.top:.4f}mm;width:{self.width:.4f}mm;height:{self.height:.4f}mm;" + (
            f"font-size:{self.size:g}pt;" if self.size else ""
        )


def _place(kind: str, box: Box, **values: Any) -> Part:
    return Part(
        kind=kind,
        left=box.x * MM_PER_PT,
        top=box.y * MM_PER_PT,
        width=box.w * MM_PER_PT,
        height=box.h * MM_PER_PT,
        **values,
    )


def ink_rise(text: str) -> float:
    """How far the ink of a text reaches above its baseline, in em: ascenders and capitals, or capitals with an accent."""
    tall = any(character.isupper() and len(unicodedata.normalize("NFD", character)) > 1 for character in text)
    return INK_RISE_ACCENT if tall else INK_RISE


def _text(spec: TextSpec, text: str, *, box: Box | None = None, top: float | None = None) -> Part | None:
    """A text fitted to its box; with ``top`` (the upper end of the area) also small enough that its ink stays below it.

    The text stands in the middle of its box: its baseline lies :data:`BASELINE_BELOW_MIDDLE` em below it.
    """
    if not text:
        return None
    place = box or spec.box
    size = fit_size(text, spec.size, place.w)
    if top is not None:
        room = place.y + place.h / 2 - top
        size = min(size, max(MIN_SIZE_PT, math.floor(room / (ink_rise(text) - BASELINE_BELOW_MIDDLE) * 100) / 100))
    return _place("text", place, size=size, align=spec.align, text=text)


@dataclass
class LabelText:
    """What one label says – the company's settings with the item's ID and what its QR code holds."""

    name: str
    phone_line: str
    id_caption: str
    display_id: str
    url: str
    notice: str
    wrap_text: str
    #: The logo file as it was uploaded (PNG or JPEG); made black and white for each label (:func:`print_logo`).
    logo: bytes
    qr_content: str
    #: The cable label has less room: its own (shorter) name, the phone number without words before it, and "ID:".
    cable_name: str = ""
    phone: str = ""


@dataclass
class LaidOutLabel:
    """A label ready to draw: its size, its parts and the area the printer can print (millimetres)."""

    width_mm: float
    height_mm: float
    parts: list[Part]
    printable: Part | None = None
    #: Cable label: the blank start in millimetres, and whether the length set is too short for the template's.
    lead_in_mm: float = 0.0
    lead_in_shortened: bool = False


def qr_zone(layout: Layout, area: Box) -> Box:
    """Where the QR code of the small and the large label may grow (labels like the originals; MAT-085).

    From the upper left corner of the box in which the template draws it to
    the right and lower end of the area used: P-touch's 47.5 points leave
    the QR code of a long address room only a little larger than it is.
    """
    return Box(layout.qr.x, layout.qr.y, area.right - layout.qr.x, area.bottom - layout.qr.y)


def qr_part(
    content: str, zone: Box, *, align: str = "right", left: float = 0.0, right: float = 0.0, bottom: float = 0.0
) -> tuple[Part, Box]:
    """The QR code as large as its zone allows, and the rectangle it keeps free of texts (MAT-065).

    The modules are as large as the zone has room for after the quiet zone
    that must stay free inside it (``left``, ``right`` and ``bottom``, in
    modules): whole printer dots where that costs at most
    :data:`QR_WHOLE_DOT_SHARE` of the size – each module prints alike –, else
    fractions of a dot, as P-touch's cells are. The drawing stands at the
    right (``align`` "right") or the left of the zone and at its bottom. The
    free rectangle adds :data:`QR_GAP` modules on its left and its top.
    """
    drawing = qr_drawing(content)
    modules = drawing.modules
    exact = max(1.0, min(zone.w / DOT_PT / (modules + left + right), zone.h / DOT_PT / (modules + bottom)))
    whole = math.floor(exact + 1e-9)
    dots = float(whole) if whole >= QR_WHOLE_DOT_SHARE * exact else math.floor(exact * 100) / 100
    module = dots * DOT_PT
    side = modules * module
    x = zone.right - right * module - side if align == "right" else zone.x + left * module
    y = zone.bottom - bottom * module - side
    gap = QR_GAP * module
    return _place("qr", Box(x, y, side, side), content=drawing.svg), Box(x - gap, y - gap, side + gap, side + gap)


def logo_part(data: bytes, box: Box) -> Part | None:
    """The logo in black and white, as large as fits its box, in the middle of it, on whole dots."""
    if not data:
        return None
    url, width, height = print_logo(data, _dots(box.w), _dots(box.h))
    if not url:
        return None
    x = box.x + round((box.w - width * DOT_PT) / 2 / DOT_PT) * DOT_PT
    y = box.y + round((box.h - height * DOT_PT) / 2 / DOT_PT) * DOT_PT
    return _place("logo", Box(x, y, width * DOT_PT, height * DOT_PT), content=url)


def lay_out(layout: Layout, text: LabelText, *, length_mm: float | None = None) -> LaidOutLabel:
    """Place the parts of one label as the template does (MAT-056), inside the printable area (MAT-065)."""
    if layout.kind == CABLE.kind:
        return _lay_out_cable(layout, text, float(length_mm or layout.height_mm))
    area = usable_area(layout.kind)
    parts: list[Part] = []

    def add(part: Part | None) -> None:
        if part is not None:
            parts.append(part)

    qr, keep = qr_part(text.qr_content, qr_zone(layout, area), bottom=QR_BOTTOM_MARGIN)
    limit = keep.x
    logo = logo_part(text.logo, layout.logo)
    name_box = layout.name.box
    if logo is None:
        # Without a logo the name takes its place as well.
        name_box = Box(layout.logo.x, name_box.y, name_box.right - layout.logo.x, name_box.h)
    add(logo)
    # The title stands above the QR code, as wide as the label.
    add(_text(layout.name, text.name, box=name_box, top=area.y))
    add(qr)
    add(_text(layout.phone, text.phone_line, box=layout.phone.box.up_to(limit)))
    add(_text(layout.url, text.url, box=layout.url.box.up_to(limit)))
    add(_text(layout.ident, f"{text.id_caption} {text.display_id}".strip(), box=layout.ident.box.up_to(limit)))
    if layout.notice is not None and text.notice:
        box = layout.notice.box.up_to(limit)
        size, lines = fit_block(text.notice, layout.notice.size, box.w, box.h)
        add(_place("lines", box, size=size, align=layout.notice.align, lines=lines))
    return LaidOutLabel(layout.width_mm, layout.height_mm, parts, printable=_place("area", printable_area(layout.kind)))


def _lay_out_cable(layout: Layout, text: LabelText, length_mm: float) -> LaidOutLabel:
    """The cable label as in the template, moved to the end of the label (labels like the originals; MAT-085).

    QR code and logo at the left, the column of name, web address, phone number and ID beside them, the repeated
    text above.
    """
    area = usable_area(layout.kind, length_mm)
    parts: list[Part] = []
    shift = area.bottom - CABLE_TEMPLATE_BOTTOM
    column = layout.name.box.x + SIDE_SAFETY_DOTS[layout.kind] * DOT_PT

    def add(part: Part | None) -> None:
        if part is not None:
            parts.append(part)

    def moved(box: Box) -> Box:
        return Box(box.x, box.y + shift, box.w, box.h)

    def in_column(box: Box) -> Box:
        """A row of the column of texts, moved down and starting at ``column`` (its right end stays)."""
        row_box = moved(box)
        start = max(row_box.x, column)
        return Box(start, row_box.y, row_box.right - start, row_box.h)

    # The QR code left of the column of texts, at the lower end; a module of quiet zone before the texts.
    zone = Box(area.x, layout.qr.y + shift, column - area.x, layout.qr.h)
    qr, _keep = qr_part(text.qr_content, zone, align="left", right=1)
    row = in_column(layout.name.box)
    logo = logo_part(text.logo, moved(layout.logo))
    name_box = row
    if logo is None:
        # Without a logo the name takes its place as well.
        name_box = Box(layout.logo.x, row.y, row.right - layout.logo.x, row.h)
    add(logo)
    add(_text(layout.name, text.cable_name or text.name, box=name_box))
    add(_text(layout.url, text.url, box=in_column(layout.url.box)))
    add(_text(layout.phone, text.phone, box=in_column(layout.phone.box)))
    ident = in_column(layout.ident.box)
    caption = "ID:"
    size = fit_size(f"{caption}  {text.display_id}", layout.ident.size, ident.w)
    add(_place("pair", ident, size=size, text=caption, right=text.display_id))
    add(qr)
    # The blank start as in the template; shorter only where the label is too short for it, one repeat and the rows.
    wrap_height = layout.wrap.box.h if layout.wrap is not None else 0.0
    lead_in = max(area.y, min(LEAD_IN_PT, row.y - 2.0 - wrap_height))
    if layout.wrap is not None and text.wrap_text:
        for top in wrap_positions(lead_in, row.y - 2.0, wrap_height):
            add(_text(layout.wrap, text.wrap_text, box=Box(area.x, top, area.w, wrap_height)))
    return LaidOutLabel(
        layout.width_mm,
        length_mm,
        parts,
        printable=_place("area", printable_area("cable", length_mm)),
        lead_in_mm=lead_in * MM_PER_PT,
        lead_in_shortened=lead_in < LEAD_IN_PT - 1e-6,
    )


def wrap_positions(top: float, bottom: float, height: float) -> list[float]:
    """Where the text around the cable stands: from the end of the blank start on, evenly, at most 14 mm apart.

    As in the template (14 mm apart) – a longer label gets more repeats, a
    shorter one fewer. Too little room for two: once, at the top; for none: never.
    """
    free = bottom - top - height
    if free < 0:
        return []
    count = math.ceil(free / WRAP_STEP_PT - 1e-9) + 1
    step = free / (count - 1) if count > 1 else 0.0
    if count > 1 and step < 2 * height:
        return [top]
    return [top + index * step for index in range(count)]


def sample_text() -> LabelText:
    """An empty text for a label without items (the size of the page only)."""
    return LabelText("", "", "", "", "", "", "", b"", "")
