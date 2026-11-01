# SPDX-License-Identifier: GPL-3.0-or-later
"""The timesheet as a printable PDF (ZEI-017).

Like the packlist, the PDF is an HTML template
(``timetracking/timesheet_pdf.html``) turned into pages by WeasyPrint. Fonts
come from the installation itself; nothing is loaded from the internet
(NFA-050).
"""

from __future__ import annotations

from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.models import CompanyProfile
from rentalars.core.money import group_thousands
from rentalars.packing.pdf import _font_url
from rentalars.timetracking.services import HoursReport

#: The most entries one timesheet may hold. Laying out the pages is the slow part: on the
#: test machine (2 cores) a month of 100 people – 2,200 entries, 78 pages – took about 15
#: seconds. Without a limit, a year of everybody would run past the time the server allows a
#: request (120 seconds) and end in an error page instead of a timesheet.
MAX_TIMESHEET_ENTRIES = 3000


def timesheet_is_too_long(report: HoursReport) -> bool:
    """Whether a timesheet of this report would hold more entries than :data:`MAX_TIMESHEET_ENTRIES`."""
    return len(report.entries) > MAX_TIMESHEET_ENTRIES


def too_long_message(report: HoursReport) -> str:
    """Explain why the timesheet is not made, and what to do instead."""
    return _(
        "The timesheet would hold %(count)s entries. More than %(limit)s at once would keep the server busy for "
        "too long – please narrow it down by person, project or period. The CSV file has no such limit."
    ) % {"count": group_thousands(str(len(report.entries))), "limit": group_thousands(str(MAX_TIMESHEET_ENTRIES))}


def render_timesheet_html(report: HoursReport, period: str = "") -> str:
    """Render an hours report as the HTML document the PDF is made from.

    One block per row of the report (a person, a project …) with its entries
    – day, times, break, hours – and the sum; at the end the total and a
    line to sign. Amounts appear where the report carries them, that is
    where the reader may see the rates (AUT-019). Hints at conspicuous
    entries are printed under them (ZEI-018).
    """
    from rentalars.timetracking.hints import attach_hints

    if report.entries and not hasattr(report.entries[0], "hints"):
        attach_hints(report.entries)
    return render_to_string(
        "timetracking/timesheet_pdf.html",
        {
            "report": report,
            "period": period,
            "company": CompanyProfile.load(),
            "printed_at": timezone.localtime(),
            "fonts": {
                "regular": _font_url("barlow-latin-400-normal.woff2"),
                "semibold": _font_url("barlow-latin-600-normal.woff2"),
                "condensed": _font_url("barlow-condensed-latin-600-normal.woff2"),
            },
        },
    )


def render_timesheet_pdf(report: HoursReport, period: str = "") -> bytes:
    """Return an hours report as PDF bytes: the timesheet (ZEI-017)."""
    # Imported here because loading WeasyPrint takes a noticeable moment and
    # only this function needs it.
    from weasyprint import HTML

    return HTML(string=render_timesheet_html(report, period)).write_pdf()
