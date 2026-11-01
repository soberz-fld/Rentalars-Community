# SPDX-License-Identifier: GPL-3.0-or-later
"""The hours report as a file for a spreadsheet (ZEI-017).

The browser page and the API both deliver the file from here (API-002).
"""

from __future__ import annotations

import csv
import io
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights
from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_decimal, format_money
from rentalars.timetracking import services
from rentalars.timetracking.hints import hints_for

#: Marks the text as UTF-8 for spreadsheet programs; without it umlauts arrive broken.
BYTE_ORDER_MARK = "﻿"


def report_csv(report: services.HoursReport, rights: Rights, user: Any) -> str:
    """Return the entries of a report as CSV text.

    Semicolons and decimal commas, as German spreadsheet programs expect
    them. One row per entry. The columns "hourly rate" and "amount" are
    filled only where the reader may see the rate (AUT-019, PER-010). The
    last column holds the hints at the entry (ZEI-018).
    """
    if all(hasattr(entry, "hints") for entry in report.entries):
        hints = {entry.pk: entry.hints for entry in report.entries}  # noted by the page already
    else:
        hints = hints_for(report.entries)
    text = io.StringIO()
    text.write(BYTE_ORDER_MARK)
    writer = csv.writer(text, delimiter=";")
    writer.writerow(
        [
            _("Person"),
            _("Project number"),
            _("Project"),
            _("Job function"),
            _("Day"),
            _("Begin"),
            _("End"),
            _("Break (minutes)"),
            _("Hours"),
            _("Status"),
            _("Hourly rate"),
            _("Amount"),
            _("Note"),
            _("Hints"),
        ]
    )
    for entry in report.entries:
        start, end = timezone.localtime(entry.start), timezone.localtime(entry.end)
        may_see = services.may_see_rate_of(rights, user, entry.person)
        writer.writerow(
            [
                entry.person.sort_name,
                entry.project.number if entry.project_id else "",
                entry.project.name if entry.project_id else entry.project_label,
                entry.job_function.name,
                start.strftime(local_pattern("%d.%m.%Y")),
                start.strftime("%H:%M"),
                end.strftime("%H:%M"),
                entry.break_minutes,
                format_decimal(entry.hours, max_places=2),
                entry.get_status_display(),
                format_money(entry.hourly_rate, currency="").strip() if may_see else "",
                format_money(entry.amount, currency="").strip() if may_see else "",
                entry.note,
                " / ".join(hint.message for hint in hints.get(entry.pk, [])),
            ]
        )
    return text.getvalue()
