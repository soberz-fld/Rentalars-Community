# SPDX-License-Identifier: GPL-3.0-or-later
"""Documents as PDF, made with WeasyPrint from ``documents/document_pdf.html`` (DOK-005).

One HTML template serves every kind: the letterhead with logo and the
address window follow DIN 5008, the footer carries address, bank and
register details of the company. Fonts and logo come from the installation
itself; nothing is loaded from the internet (NFA-050).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string

from rentalars.documents.content import DocumentContent


def _logo_url() -> str:
    """The ``file://`` address of the company logo, or ``""``."""
    from rentalars.core.models import CompanyProfile

    logo = CompanyProfile.load().logo
    if not logo:
        return ""
    path = Path(settings.MEDIA_ROOT) / logo.name
    return path.as_uri() if path.exists() else ""


def render_html(content: DocumentContent, template: Any, *, draft: bool = False) -> str:
    """The HTML document the PDF is made from – in the language of the company's documents (UIX-029)."""
    from rentalars.core.i18n import for_documents
    from rentalars.packing.pdf import _font_url

    # Document layout: no column "Discount" when no position shown has a discount; the spans of the rows
    # that stretch over the table follow (every column but "Pos.", and the same without "Amount").
    discount_column = content.has_discounts
    with for_documents():
        return render_to_string(
            "documents/document_pdf.html",
            {
                "doc": content,
                "template": template,
                "draft": draft,
                "discount_column": discount_column,
                "span_all": 5 if discount_column else 4,
                "span_label": 4 if discount_column else 3,
                "logo": _logo_url() if template.show_logo else "",
                "fonts": {
                    "regular": _font_url("barlow-latin-400-normal.woff2"),
                    "semibold": _font_url("barlow-latin-600-normal.woff2"),
                    "condensed": _font_url("barlow-condensed-latin-600-normal.woff2"),
                },
            },
        )


def render_pdf(content: DocumentContent, template: Any, *, draft: bool = False) -> bytes:
    """The document as PDF bytes."""
    from weasyprint import HTML

    return HTML(string=render_html(content, template, draft=draft), base_url=str(settings.BASE_DIR)).write_pdf()
