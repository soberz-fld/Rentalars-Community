# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``ai_summaries``: the automatic AI summaries of projects and service cases that changed (EML-056, NFA-079).

The minute timer (``run_jobs``) starts this work as a task in the night window by itself. The command runs it by
hand, e.g. to look first what would happen::

    sudo rentalars ai_summaries --dry-run           # list the projects that would be summarised; calls no model
    sudo rentalars ai_summaries                     # run now (the opt-in under Einstellungen → KI is needed)
    sudo rentalars ai_summaries --project 42        # only this project
    sudo rentalars ai_summaries --limit 5

One run at a time: if the night's run is under way, the command says so and ends. Every run is noted for the
administrators (Einstellungen → KI → Automatische Zusammenfassungen).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from rentalars.ai import auto
from rentalars.core.audit import acting_as


class Command(BaseCommand):
    """Run the automatic summaries once, or list what they would do."""

    help = "Summarises projects and service cases that changed since their last summary (off until switched on)."

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("--dry-run", action="store_true", help="only list what would be summarised")
        parser.add_argument("--only-in-window", action="store_true", help="do nothing outside the window of the night")
        parser.add_argument("--project", type=int, help="only this project (ID)")
        parser.add_argument("--limit", type=int, help="at most this many summaries")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run and report."""
        from django.utils import timezone

        if options["only_in_window"] and not auto.in_window(timezone.localtime()):
            self.stdout.write("Not in the window of the night; nothing done.")
            return
        with acting_as(auto.PRINCIPAL):
            record = auto.run(
                dry_run=options["dry_run"],
                ignore_window=not options["only_in_window"],
                only_project=options.get("project"),
                limit=options.get("limit"),
            )
        if record is None:
            self.stdout.write("Nothing done: the automatic summaries are off, or another run is under way.")
            return
        if record.dry_run:
            noun = "project" if record.candidates == 1 else "projects"
            self.stdout.write(f"{record.candidates} {noun} would be summarised:")
            for entry in record.details:
                if entry.get("outcome") == "would":
                    self.stdout.write(
                        f"  {entry['number']} {entry.get('name', '')} – {entry['reason']}, {entry['mails']} mails"
                    )
                else:
                    self.stdout.write(f"  {entry.get('error', '')}")
            return
        self.stdout.write(auto.describe(record))
