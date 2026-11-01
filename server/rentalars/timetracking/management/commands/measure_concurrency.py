# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``measure_concurrency``: ten people record their times at once (NFA-051)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from rentalars.timetracking.loadtest import LIMIT_SECONDS, measure_concurrent_recording


class Command(BaseCommand):
    """Plays the moment after a job, when the whole crew writes down its hours."""

    help = (
        "Lets several people record and read times at the same moment, through the running server, "
        "and reports how long the answers took. Creates its own test accounts and removes them again."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("--users", type=int, default=10, help="people at the same time (default 10)")
        parser.add_argument("--rounds", type=int, default=5, help="entries each of them records (default 5)")
        parser.add_argument("--url", default=settings.RENTALARS_URL, help="address of the installation")
        parser.add_argument(
            "--insecure",
            action="store_true",
            help="do not check the certificate (test installation with a self-signed certificate)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the measurement and print the result."""
        if options["users"] < 1 or options["rounds"] < 1:
            raise CommandError("--users and --rounds must be at least 1.")
        result = measure_concurrent_recording(
            options["url"], users=options["users"], rounds=options["rounds"], verify_tls=not options["insecure"]
        )
        self.stdout.write(
            f"{result.users} people at the same moment, {result.rounds} entries each, without pause "
            f"({result.total_seconds:.1f} s in total) at {options['url']}"
        )
        for step, label in (("record", "record a time"), ("read", "read the own times")):
            verdict = self.style.SUCCESS("ok") if result.slowest(step) < LIMIT_SECONDS else self.style.ERROR("TOO SLOW")
            self.stdout.write(
                f"  {label:20} median {result.median(step) * 1000:5.0f} ms   slowest "
                f"{result.slowest(step) * 1000:5.0f} ms   (limit {LIMIT_SECONDS * 1000:.0f} ms)  {verdict}"
            )
        self.stdout.write(f"  entries saved: {result.entries_saved} of {result.entries_expected}")
        for error in result.errors[:10]:
            self.stdout.write(self.style.ERROR(f"  {error}"))
        if not result.ok:
            raise CommandError("The installation did not stay usable with this many people at once.")
        self.stdout.write(self.style.SUCCESS("Stayed usable."))
