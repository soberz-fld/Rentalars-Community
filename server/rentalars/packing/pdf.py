# SPDX-License-Identifier: GPL-3.0-or-later
"""The packlist as a printable PDF (PCK-003, DOK-001).

The PDF is an HTML template (``packing/packlist_pdf.html``) turned into pages
by the library WeasyPrint. Layout changes are therefore made in HTML and CSS,
not in code. Fonts come from the installation itself; nothing is loaded from
the internet (NFA-050).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.utils import timezone

from rentalars.core.i18n import FILE_NAMES, file_name, for_documents
from rentalars.core.models import CompanyProfile
from rentalars.packing.services import PackOverview

if TYPE_CHECKING:
    from rentalars.packing.subprojects import FamilyPacklist


def _font_url(file_name: str) -> str:
    """Return the ``file://`` address of a font shipped in ``static/fonts``."""
    path = finders.find(f"fonts/{file_name}")
    return Path(path).as_uri() if path else ""


def _fonts() -> dict[str, str]:
    """The fonts of the printed packlists."""
    return {
        "regular": _font_url("barlow-latin-400-normal.woff2"),
        "semibold": _font_url("barlow-latin-600-normal.woff2"),
        "condensed": _font_url("barlow-condensed-latin-600-normal.woff2"),
    }


def packing_list_name(project: Any, suffix: str = "", *, whole: bool = False) -> str:
    """``Packliste-2026-0042.pdf`` – in the language of the company's documents, as the list itself (UIX-029)."""
    with for_documents():
        return file_name(
            "packing_list", f"{project.number}{suffix}", FILE_NAMES["whole"] if whole else "", extension="pdf"
        )


def render_packlist_html(overview: PackOverview, *, show_customer: bool = True) -> str:
    """Render the packlist as the HTML document the PDF is made from.

    The document contains the project header (project, customer, venue,
    period, project manager), one row per thing to pack with a box to tick,
    and no prices at all (PCK-007).

    Args:
        overview: The packlist with its rows.
        show_customer: ``False`` leaves the customer out – for crew who see
            the project only through its deployment view (AUT-023).
    """
    project = overview.packlist.project
    # UIX-029: a packing list may go out with the goods – in the language of the company's documents.
    with for_documents():
        return render_to_string(
            "packing/packlist_pdf.html",
            {
                "overview": overview,
                "project": project,
                "show_customer": show_customer,
                "company": CompanyProfile.load(),
                "printed_at": timezone.localtime(),
                "fonts": _fonts(),
            },
        )


def render_packlist_pdf(overview: PackOverview, *, show_customer: bool = True) -> bytes:
    """Return the packlist of a project as PDF bytes (PCK-003); see :func:`render_packlist_html`."""
    # Imported here because loading WeasyPrint takes a noticeable moment and
    # only this function needs it.
    from weasyprint import HTML

    return HTML(string=render_packlist_html(overview, show_customer=show_customer)).write_pdf()


def render_family_html(family: FamilyPacklist, *, view: str, show_customer: bool = True) -> str:
    """Render the packlist of a whole project with all its parts (PRJ-048) as HTML for the PDF.

    Args:
        family: The packlists of the parts the user may see.
        view: ``parts`` – part by part, as each is loaded – or ``articles`` –
            summed up per article, for picking in the warehouse.
        show_customer: ``False`` leaves the customer out (AUT-023).
    """
    with for_documents():  # UIX-029, as the packing list of a single project
        return render_to_string(
            "packing/family_pdf.html",
            {
                "family": family,
                "project": family.whole,
                "view": view,
                "show_customer": show_customer,
                "company": CompanyProfile.load(),
                "printed_at": timezone.localtime(),
                "fonts": _fonts(),
            },
        )


def render_family_pdf(family: FamilyPacklist, *, view: str, show_customer: bool = True) -> bytes:
    """Return the packlist of a whole project with all its parts as PDF bytes (PRJ-048, PCK-003)."""
    from weasyprint import HTML

    return HTML(string=render_family_html(family, view=view, show_customer=show_customer)).write_pdf()
