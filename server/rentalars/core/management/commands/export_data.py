# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``export_data``: write the full export of all data into a ZIP file (IMP-006).

Example::

    sudo rentalars export_data /var/lib/rentalars/rentalars-export.zip

The same archive as "Make a full export" in the settings (IMP-006; on the
page "Backup"): every table as JSON and CSV and all stored files, without
passwords and other secrets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from rentalars.core.audit import record_event
from rentalars.core.export import write_export
from rentalars.core.models import SystemSettings


class Command(BaseCommand):
    """Writes the archive and reports what it contains."""

    help = "Writes all data and files into one ZIP file (JSON and CSV), without passwords and other secrets."

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("target", help="path of the ZIP file to write")

    def handle(self, *args: Any, **options: Any) -> None:
        """Write the archive."""
        target = Path(options["target"])
        if target.exists():
            raise CommandError(f"{target} exists already.")
        counts = write_export(target)
        record_event(SystemSettings.load(), "export.full", {"by": "rentalars export_data", "file": str(target)})
        files = counts.pop("files")
        self.stdout.write(
            f"{len(counts)} tables with {sum(counts.values())} rows and {files} files written to {target}."
        )
