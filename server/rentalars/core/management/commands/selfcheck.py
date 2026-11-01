# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``selfcheck``: the state of the installation (NFA-037).

    sudo rentalars selfcheck

prints the same findings as the page "Self-check" of the administration and
ends with exit status 1 if one of them is an error – usable in a monitoring
script.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from rentalars.core.selfcheck import ERROR, NOTE, OK, WARNING, run_checks

_MARKS = {OK: "ok  ", NOTE: "i   ", WARNING: "!   ", ERROR: "XX  "}


class Command(BaseCommand):
    """Prints the findings of the self-check, grouped."""

    help = "Checks versions, database, files, mail, backup, free space and security settings."

    def handle(self, *args: Any, **options: Any) -> None:
        """Print every finding; fail if there is an error."""
        report = run_checks()
        for group, findings in report.groups():
            self.stdout.write(f"\n{group}")
            for finding in findings:
                line = f"  {_MARKS[finding.state]}{finding.title}"
                if finding.detail:
                    line += f": {finding.detail}"
                self.stdout.write(line)
        labels = {OK: _("everything in order"), NOTE: _("notes"), WARNING: _("warnings"), ERROR: _("errors")}
        self.stdout.write(f"\n{_('Result')}: {labels[report.worst]}")
        if report.worst == ERROR:
            raise SystemExit(1)
