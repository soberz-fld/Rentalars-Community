# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``sync_calendars``: read linked calendars and write CalDAV calendars now (PER-022, PER-023, PER-031).

The background timer does the same every minute for whatever is due (see
``run_jobs``). By hand, for checking a setup or after a longer outage::

    manage.py sync_calendars                # what is due
    manage.py sync_calendars --person 17    # one person, due or not
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from rentalars.core.audit import acting_as
from rentalars.personnel.calendars import run_due, sync_person
from rentalars.personnel.models import Person


class Command(BaseCommand):
    """Read and write the calendars of the people."""

    help = "Reads the linked calendars of the people and writes their deployments into their CalDAV calendars."

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("--person", type=int, help="only this person (ID), whether due or not")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run and report."""
        with acting_as("system:calendars"):
            if options.get("person"):
                person = Person.objects.filter(pk=options["person"]).first()
                if person is None:
                    raise CommandError(f"There is no person with the ID {options['person']}.")
                _feed, push = sync_person(person, budget_seconds=600)
                # PER-031: one line per linked calendar, named by its server – the address is a secret.
                for calendar in person.calendar_feeds.all():
                    outcome = f"failed: {calendar.error}" if calendar.error else "read"
                    self.stdout.write(f"Linked calendar {calendar.name}: {outcome}")
                if push is not None:
                    outcome = (
                        f"failed: {push.error}"
                        if push.error
                        else f"{push.written} written, {push.deleted} deleted, {push.unchanged} unchanged"
                    )
                    self.stdout.write(f"CalDAV calendar: {outcome}")
                return
            result = run_due(budget_seconds=600)
        if options["verbosity"] > 0:
            self.stdout.write(
                f"Linked calendars: {result.feeds_read} read, {result.feeds_failed} failed. "
                f"CalDAV calendars: {result.calendars_written} written, {result.calendars_failed} failed."
            )
