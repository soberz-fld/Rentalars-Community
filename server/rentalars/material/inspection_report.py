# SPDX-License-Identifier: GPL-3.0-or-later
"""The printable protocol of an electrical inspection (MAT-078; MAT-031).

One page per inspection: the company, the item (ID, model, serial number, protection class), date,
inspector and test device, every value with its limit and verdict (``material.dguv``), the result and the
note, and a line to sign. Made like the other documents: an HTML template
(``material/inspection_report_pdf.html``) turned into a PDF by WeasyPrint, in the language of the
company's documents (UIX-029); fonts and logo come from the installation itself (NFA-050).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import pgettext

from rentalars.core.i18n import for_documents
from rentalars.core.models import CompanyProfile
from rentalars.material.inspections import add_months
from rentalars.material.models import Inspection


def _font_url(name: str) -> str:
    """The ``file://`` address of a font shipped in ``static/fonts``."""
    path = finders.find(f"fonts/{name}")
    return Path(path).as_uri() if path else ""


def _logo_url(company: CompanyProfile) -> str:
    """The ``file://`` address of the company logo, or ``""``."""
    if not company.logo:
        return ""
    path = Path(settings.MEDIA_ROOT) / company.logo.name
    return path.as_uri() if path.exists() else ""


def report_file_name(inspection: Inspection) -> str:
    """``Pruefprotokoll-0042-2027-02-26.pdf`` – in the language of the company's documents."""
    with for_documents():
        word = pgettext("file name", "Inspection-report")
    return f"{word}-{inspection.item.display_id}-{inspection.date.isoformat()}.pdf"


def render_report_html(inspection: Inspection) -> str:
    """The protocol as the HTML document the PDF is made from."""
    company = CompanyProfile.load()
    item = inspection.item
    next_due = add_months(inspection.date, inspection.inspection_type.interval_months) if inspection.passed else None
    context: dict[str, Any] = {
        "inspection": inspection,
        "item": item,
        "evaluation": inspection.evaluation,
        "company": company,
        "logo": _logo_url(company),
        "next_due": next_due,
        "printed_at": timezone.localtime(),
        "fonts": {
            "regular": _font_url("barlow-latin-400-normal.woff2"),
            "semibold": _font_url("barlow-latin-600-normal.woff2"),
            "condensed": _font_url("barlow-condensed-latin-600-normal.woff2"),
        },
    }
    with for_documents():
        return render_to_string("material/inspection_report_pdf.html", context)


def render_report_pdf(inspection: Inspection) -> bytes:
    """The protocol of an electrical inspection as PDF bytes; see :func:`render_report_html`."""
    # Imported here: loading WeasyPrint takes a noticeable moment and only this function needs it.
    from weasyprint import HTML

    return HTML(string=render_report_html(inspection), base_url=str(settings.BASE_DIR)).write_pdf()
