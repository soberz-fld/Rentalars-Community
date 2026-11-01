# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``create_load_test_data``: fill a test installation for the performance proof (scenario 11)."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from rentalars.core.loadtest import LoadTestSize, create_load_test_data


class Command(BaseCommand):
    """Creates 100 users, 20,000 material items and 1,000 projects (NFA-006 to NFA-010)."""

    help = (
        "Creates the amount of data of acceptance scenario 11: 100 users, 20,000 material items, 1,000 projects "
        "and one project with 500 lines in 20 groups. Only for a test installation."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        defaults = LoadTestSize()
        parser.add_argument("--users", type=int, default=defaults.users)
        parser.add_argument("--items", type=int, default=defaults.items)
        parser.add_argument("--projects", type=int, default=defaults.projects)
        parser.add_argument(
            "--force",
            action="store_true",
            help="create the data although the installation already has customers or projects",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Create the data and print how much was created."""
        size = LoadTestSize(users=options["users"], items=options["items"], projects=options["projects"])
        try:
            created = create_load_test_data(size, force=options["force"])
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        for name, count in created.items():
            self.stdout.write(f"  {name:<16} {count:>7}")
        self.stdout.write(self.style.SUCCESS("Load test data created."))
