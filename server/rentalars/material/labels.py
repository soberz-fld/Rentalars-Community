# SPDX-License-Identifier: GPL-3.0-or-later
"""Labels for material items: ID, short name and a code to scan (MAT-026).

Two kinds of code can be printed:

* a **QR code** holding the address of the item's page, e.g.
  ``https://rentalars.example.de/m/0042`` – a phone camera opens it, and a
  later scan function (MAT-027) can read the ID from it;
* a **barcode** (Code 128) holding the ID alone, for hand scanners.

Labels come on A4 sheets or one per page for a label printer
(:data:`FORMATS`). The PDF is made with WeasyPrint, like the packlist; the
codes are SVG drawn here, so nothing is loaded from outside.

MAT-056: three labels for Brother label printers are the standard –
small 17 × 54 mm, large 29 × 90 mm and the cable label on the 29 mm roll –,
laid out like the operator's P-touch templates (``material.label_layouts``)
with logo, name, phone number, web address, text and QR code from
Einstellungen → Etiketten (``LabelSettings``). They come as a PDF and as a
page that opens the print dialog of the browser at once, one label per page
in its exact size (:func:`render_labels_html` with ``for_browser``).

MAT-065 (labels): the three are set in Liberation Sans (Arial's metrics, as the
templates) and lie inside the area the printer prints (``material.label_layouts``);
the sheets of MAT-026 stay as they were.

(labels like the originals; MAT-085): the design follows the templates again – the
title as wide as the label, the QR code in the place it has there, grown to the
free space of that place.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext_lazy as _

from rentalars.core.i18n import file_name
from rentalars.material.models import MaterialItem

#: The most labels in one PDF made while the user waits; more go to the background (NFA-041).
MAX_LABELS_DIRECT = 240

#: The most labels in one batch at all.
MAX_LABELS = 5000


@dataclass(frozen=True)
class LabelFormat:
    """A sheet or roll of labels: page size, label size, how many across and down."""

    key: str
    name: Any
    page_width_mm: float
    page_height_mm: float
    label_width_mm: float
    label_height_mm: float
    columns: int
    rows: int
    margin_top_mm: float = 0
    margin_left_mm: float = 0
    gap_x_mm: float = 0
    gap_y_mm: float = 0

    @property
    def per_page(self) -> int:
        """How many labels fit on one page."""
        return self.columns * self.rows

    @property
    def is_small(self) -> bool:
        """Small labels get the ID and the code only."""
        return self.label_height_mm < 25


FORMATS = {
    "a4-24": LabelFormat("a4-24", _("A4, 24 labels 70 × 37 mm (3 × 8)"), 210, 297, 70, 37, 3, 8, margin_top_mm=0.5),
    "a4-65": LabelFormat(
        "a4-65",
        _("A4, 65 labels 38.1 × 21.2 mm (5 × 13)"),
        210,
        297,
        38.1,
        21.2,
        5,
        13,
        margin_top_mm=10.7,
        margin_left_mm=4.7,
        gap_x_mm=2.5,
    ),
    "roll-62x29": LabelFormat("roll-62x29", _("Label printer, 62 × 29 mm, one per label"), 62, 29, 62, 29, 1, 1),
}

#: The format; the pages suggest the label of Einstellungen → Etiketten
#: (:func:`default_format`). The API keeps this one when a program names no format.
DEFAULT_FORMAT = "a4-24"


def default_format() -> str:
    """MAT-056: the label suggested – as set under Einstellungen → Etiketten, at first the small one."""
    from rentalars.material.models import LabelSettings

    return LabelSettings.load().default_kind


def format_choices() -> list[tuple[str, Any]]:
    """Every format: the three labels of MAT-056 first, then the sheets and the roll."""
    from rentalars.material.models import LabelKind

    return [*LabelKind.choices, *((key, sheet.name) for key, sheet in FORMATS.items())]


def is_layout(label_format: str) -> bool:
    """Whether a format is one of the three labels of MAT-056 (always with a QR code)."""
    from rentalars.material.label_layouts import LAYOUTS

    return label_format in LAYOUTS


def all_formats() -> list[str]:
    """The keys of every format, for checking what an API caller sent."""
    return [key for key, _label in format_choices()]


CODE_QR, CODE_BARCODE = "qr", "barcode"
CODE_CHOICES = [(CODE_QR, _("QR code (opens the item's page)")), (CODE_BARCODE, _("Barcode (Code 128, the ID)"))]


# --- Code 128 -----------------------------------------------------------------------------------

# The bar patterns of Code 128, values 0 to 106: widths of bar, space, bar, …
# in modules. 106 is the stop pattern (with its final bar of two modules).
_PATTERNS = [
    "212222",
    "222122",
    "222221",
    "121223",
    "121322",
    "131222",
    "122213",
    "122312",
    "132212",
    "221213",
    "221312",
    "231212",
    "112232",
    "122132",
    "122231",
    "113222",
    "123122",
    "123221",
    "223211",
    "221132",
    "221231",
    "213212",
    "223112",
    "312131",
    "311222",
    "321122",
    "321221",
    "312212",
    "322112",
    "322211",
    "212123",
    "212321",
    "232121",
    "111323",
    "131123",
    "131321",
    "112313",
    "132113",
    "132311",
    "211313",
    "231113",
    "231311",
    "112133",
    "112331",
    "132131",
    "113123",
    "113321",
    "133121",
    "313121",
    "211331",
    "231131",
    "213113",
    "213311",
    "213131",
    "311123",
    "311321",
    "331121",
    "312113",
    "312311",
    "332111",
    "314111",
    "221411",
    "431111",
    "111224",
    "111422",
    "121124",
    "121421",
    "141122",
    "141221",
    "112214",
    "112412",
    "122114",
    "122411",
    "142112",
    "142211",
    "241211",
    "221114",
    "413111",
    "241112",
    "134111",
    "111242",
    "121142",
    "121241",
    "114212",
    "124112",
    "124211",
    "411212",
    "421112",
    "421211",
    "212141",
    "214121",
    "412121",
    "111143",
    "111341",
    "131141",
    "114113",
    "114311",
    "411113",
    "411311",
    "113141",
    "114131",
    "311141",
    "411131",
    "211412",
    "211214",
    "211232",
    "2331112",
]

_START_B, _START_C, _STOP = 104, 105, 106
#: In code set C: switch to code set B.
_CODE_B = 100


def code128_values(text: str) -> list[int]:
    """The symbol values for a text, with start, check and stop symbol.

    A text of digits only is written in code set C, two digits per symbol –
    an ID such as 0042 gets a short barcode. With an odd number of digits
    (10000) the last one follows in code set B. Everything else uses code
    set B (printable ASCII).

    Raises:
        ValueError: The text contains characters Code 128 B cannot hold.
    """
    if text.isdigit() and text.isascii() and len(text) >= 2:
        even = len(text) - len(text) % 2
        values = [_START_C] + [int(text[index : index + 2]) for index in range(0, even, 2)]
        if even < len(text):
            values += [_CODE_B, ord(text[-1]) - 32]
    else:
        if any(not 32 <= ord(character) <= 126 for character in text):
            raise ValueError("Code 128 B holds printable ASCII only")
        values = [_START_B] + [ord(character) - 32 for character in text]
    check = (values[0] + sum(position * value for position, value in enumerate(values[1:], start=1))) % 103
    return [*values, check, _STOP]


def code128_modules(text: str) -> str:
    """The barcode as a string of ``1`` (bar) and ``0`` (space), one character per module."""
    modules = []
    for value in code128_values(text):
        for index, width in enumerate(_PATTERNS[value]):
            modules.append(("1" if index % 2 == 0 else "0") * int(width))
    return "".join(modules)


def code128_svg(text: str, *, height: float = 30, module: float = 1) -> SafeString:
    """The barcode as an SVG drawing with a quiet zone of ten modules on each side."""
    bars = code128_modules(text)
    quiet = 10
    width = (len(bars) + 2 * quiet) * module
    rectangles = []
    position = 0
    while position < len(bars):
        if bars[position] == "1":
            end = position
            while end < len(bars) and bars[end] == "1":
                end += 1
            rectangles.append(
                f'<rect x="{(quiet + position) * module:g}" y="0" width="{(end - position) * module:g}" height="{height:g}"/>'
            )
            position = end
        else:
            position += 1
    return mark_safe(  # noqa: S308 - built from numbers only
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
        f'preserveAspectRatio="none" role="img" aria-label="{text}"><g fill="#000">{"".join(rectangles)}</g></svg>'
    )


# --- QR code ------------------------------------------------------------------------------------


def item_address(item: MaterialItem) -> str:
    """The short address a QR code points to: ``…/m/0042`` (see ``material.views.item_by_code``)."""
    return f"{settings.RENTALARS_URL}/m/{item.display_id}"


def qr_svg(content: str) -> SafeString:
    """A QR code as SVG, black on white, without a fixed size (the label sets it)."""
    import segno

    output = io.BytesIO()
    segno.make(content, error="m").save(output, kind="svg", border=1, xmldecl=False, svgns=True, omitsize=True)
    return mark_safe(output.getvalue().decode("utf-8"))  # noqa: S308 - made by segno from our own text


# --- The PDF ------------------------------------------------------------------------------------


@dataclass
class Label:
    """One label as the template draws it."""

    item: MaterialItem
    code: SafeString

    @property
    def text(self) -> str:
        """The name printed under the ID."""
        return self.item.material_model.display_short_name

    @property
    def owner(self) -> str:
        """PRD-043: "Eigentum von Band X" for customer material, printed instead of the own company; else ""."""
        return owner_text(self.item)


def owner_text(item: MaterialItem) -> str:
    """PRD-043: "Eigentum von Band X" for customer material; "" for the own and for an item without model."""
    if item.material_model_id is None:
        return ""
    product = item.product
    if product is None or product.owner_id is None:
        return ""
    return _("Owned by %(owner)s") % {"owner": product.owner.name}


def build_labels(items: list[MaterialItem], code: str) -> list[Label]:
    """The labels for some items, with their codes."""
    labels = []
    for item in items:
        drawing = code128_svg(item.display_id) if code == CODE_BARCODE else qr_svg(item_address(item))
        labels.append(Label(item=item, code=drawing))
    return labels


def _fonts(*, for_browser: bool) -> dict[str, str]:
    """The fonts of the labels: files for WeasyPrint, addresses of the static files for the browser.

    MAT-065: ``label`` is the font of the three labels of MAT-056 (Liberation Sans, Arial's metrics).
    """
    from django.templatetags.static import static

    from rentalars.material.label_layouts import FONT_FILE
    from rentalars.packing.pdf import _font_url

    names = {
        "regular": "barlow-latin-400-normal.woff2",
        "semibold": "barlow-latin-600-normal.woff2",
        "condensed": "barlow-condensed-latin-600-normal.woff2",
        "label": FONT_FILE.removeprefix("fonts/"),
    }
    if for_browser:
        return {key: static(f"fonts/{name}") for key, name in names.items()}
    return {key: _font_url(name) for key, name in names.items()}


def layout_texts(items: list[MaterialItem]) -> list[Any]:
    """MAT-056: what each label of the three standard ones says – the company's settings, the item's ID and QR code.

    The logo is the one for labels, else that of the company. Customer
    material (PRD-043) names its owner instead of the company.
    """
    from rentalars.core.models import CompanyProfile
    from rentalars.material.label_layouts import LabelText, read_image
    from rentalars.material.models import LabelSettings

    settings_row = LabelSettings.load()
    logo = read_image(settings_row.logo) or read_image(CompanyProfile.load().logo)
    phone = settings_row.printed_phone
    phone_line = f"{settings_row.phone_caption} {phone}".strip() if phone else ""
    texts = []
    for item in items:
        owner = owner_text(item)
        texts.append(
            LabelText(
                name=str(owner) if owner else settings_row.printed_name,
                phone_line=phone_line,
                id_caption=settings_row.id_caption,
                display_id=item.display_id,
                url=settings_row.printed_url,
                notice=settings_row.notice,
                wrap_text=settings_row.printed_wrap_text,
                logo=logo,
                qr_content=settings_row.qr_content(item.display_id),
                cable_name=str(owner) if owner else settings_row.printed_cable_name,
                phone=phone,
            )
        )
    return texts


def render_layout_html(items: list[MaterialItem], label_format: str, *, for_browser: bool = False) -> str:
    """MAT-056: the labels small, large or cable – one label per page in its exact size."""
    from rentalars.material.label_layouts import LAYOUTS, lay_out, sample_text
    from rentalars.material.models import LabelSettings

    layout = LAYOUTS[label_format]
    cable_length = LabelSettings.load().cable_length_mm
    labels = [lay_out(layout, text, length_mm=cable_length) for text in layout_texts(items)]
    first = labels[0] if labels else lay_out(layout, sample_text(), length_mm=cable_length)
    return render_to_string(
        "material/labels_layout.html",
        {
            "labels": labels,
            "kind": label_format,
            "page_width": first.width_mm,
            "page_height": first.height_mm,
            "for_browser": for_browser,
            "fonts": _fonts(for_browser=for_browser),
        },
    )


def render_labels_html(
    items: list[MaterialItem],
    *,
    label_format: str = DEFAULT_FORMAT,
    code: str = CODE_QR,
    skip: int = 0,
    for_browser: bool = False,
) -> str:
    """The HTML document the PDF is made from; ``skip`` leaves labels free that were used already.

    MAT-056: ``for_browser`` makes the page that is printed from the browser
    itself – fonts from the server, a bar with "Drucken", and the print dialog
    opening by itself.
    """
    from rentalars.core.models import CompanyProfile

    if is_layout(label_format):
        return render_layout_html(items, label_format, for_browser=for_browser)
    sheet = FORMATS.get(label_format, FORMATS[DEFAULT_FORMAT])
    skip = max(0, min(skip, sheet.per_page - 1))
    slots: list[Label | None] = [None] * skip + build_labels(items, code)
    pages = [slots[index : index + sheet.per_page] for index in range(0, len(slots), sheet.per_page)]
    return render_to_string(
        "material/labels_pdf.html",
        {
            "sheet": sheet,
            "pages": pages,
            "code": code,
            "company": CompanyProfile.load(),
            "for_browser": for_browser,
            "fonts": _fonts(for_browser=for_browser),
        },
    )


def render_labels_pdf(items: list[MaterialItem], **options: Any) -> bytes:
    """The labels as PDF bytes (MAT-026)."""
    from weasyprint import HTML

    return HTML(string=render_labels_html(items, **options), base_url=str(settings.BASE_DIR)).write_pdf()


def run_job(job: Any) -> tuple[bytes, str]:
    """Make a large batch of labels in the background (NFA-041)."""
    from rentalars.material.label_views import chosen_items

    params = job.params
    items = chosen_items([int(number) for number in params.get("numbers", [])])
    pdf = render_labels_pdf(
        items,
        label_format=params.get("label_format") or default_format(),
        code=params.get("code", CODE_QR),
        skip=int(params.get("skip", 0) or 0),
    )
    return pdf, file_name("labels", extension="pdf")
