# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``measure_performance``: take the timings of acceptance scenario 11 (NFA-008, NFA-044).

With ``--create-test-data`` the command first fills a test installation with
the amounts of the catalogue (``create_load_test_data``) – one step to measure
the own hardware.
"""

from __future__ import annotations

import resource
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from rentalars.core.loadtest import BIG_PROJECT_NAME, LoadTestSize, create_load_test_data, measure
from rentalars.core.models import SystemSettings
from rentalars.core.warmup import set_startup_objects_aside, warm_up
from rentalars.material.models import MaterialItem
from rentalars.projects.models import Project


class Command(BaseCommand):
    """Opens the big project and adds a line, and compares the times with the limits (NFA-008)."""

    help = (
        "Measures how long the project with 500 lines takes to open and how long adding a line takes. "
        "Needs the data of create_load_test_data. Exits with an error if a limit is exceeded."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("--repeat", type=int, default=3, help="runs per step; the slowest counts (default 3)")
        parser.add_argument(
            "--create-test-data",
            action="store_true",
            help="first create the full amount of test data if it is missing (only on a test installation)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the measurement and print the result."""
        if not SystemSettings.load().setup_completed:
            # Until then every page leads to the first-run setup, and nothing could be measured.
            raise CommandError("Complete the first-run setup in the browser first (rentalars prepare_setup).")
        if options["create_test_data"] and not Project.objects.filter(name=BIG_PROJECT_NAME).exists():
            # NFA-044: one command makes the test data of the catalogue's amounts and measures on this hardware.
            self.stdout.write("Creating the test data (100 users, 20,000 items, 1,000 projects) …")
            try:
                created = create_load_test_data(LoadTestSize())
            except ValidationError as error:
                raise CommandError(" ".join(error.messages)) from error
            self.stdout.write(", ".join(f"{count} {name}" for name, count in created.items()))
        host = next((name for name in settings.ALLOWED_HOSTS if name not in {"*", ""}), "localhost")
        # Prepare this process the way the application server prepares itself
        # (rentalars/wsgi.py); otherwise the command would measure a start-up
        # the server does not have.
        warm_up()
        set_startup_objects_aside()
        try:
            timings = measure(repeat=options["repeat"], host=host)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        engine = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
        self.stdout.write(
            f"Database: {engine}; {Project.objects.count()} projects, {MaterialItem.objects.count()} material items"
        )
        for timing in timings:
            verdict = self.style.SUCCESS("ok") if timing.ok else self.style.ERROR("TOO SLOW")
            self.stdout.write(
                f"  {timing.seconds * 1000:7.0f} ms  (limit {timing.limit_seconds * 1000:5.0f} ms, "
                f"{timing.queries:3d} queries)  {timing.label}  {verdict}"
            )
        # Peak memory of this process; the limit of the scenario (4 GB) is for the whole server.
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        self.stdout.write(f"  Peak memory of this process: {peak_mb:.0f} MB")
        if not all(timing.ok for timing in timings):
            raise CommandError("At least one step exceeded its limit.")
