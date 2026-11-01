# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``import_data``: import products, customers or people from a file (IMP-001).

Examples::

    # Dry run: check the file and show what would happen. Nothing is written.
    rentalars import_data customers kunden.xlsx

    # Really import.
    rentalars import_data customers kunden.xlsx --commit

    # A column has an unusual heading: assign it by hand.
    rentalars import_data people personal.csv --map "last_name=Familienname"

The material list has a command of its own with more to report:
``rentalars import_material`` (IMP-007).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Rights
from rentalars.core import imports
from rentalars.core.tabular import ImportFileError, read_table, resolve_mapping


class Command(BaseCommand):
    """Reads an XLSX or CSV file and imports its rows; without ``--commit`` only a dry run."""

    help = (
        "Imports products, customers or people (XLSX or CSV). Without --commit only a dry run is made, "
        "which writes nothing and reports all errors with their row number."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("kind", choices=["products", "customers", "people", "material"], help="what is imported")
        parser.add_argument("file", help="path of the XLSX or CSV file")
        parser.add_argument("--commit", action="store_true", help="really import (default: dry run)")
        parser.add_argument("--sheet", help="name of the worksheet (default: the first)")
        parser.add_argument(
            "--map",
            action="append",
            default=[],
            metavar="FIELD=COLUMN",
            help='assign a column by hand, e.g. --map "name=Firma"; an empty column skips the field',
        )
        parser.add_argument("--show-mapping", action="store_true", help="only show the recognised column mapping")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the import or the dry run and print the report."""
        kind = imports.get(options["kind"])
        overrides: dict[str, str] = {}
        for assignment in options["map"]:
            if "=" not in assignment:
                raise CommandError(_("--map expects FIELD=COLUMN, not: %(value)s") % {"value": assignment})
            key, column = assignment.split("=", 1)
            overrides[key.strip()] = column.strip()
        try:
            table = read_table(options["file"], sheet=options["sheet"])
            mapping = resolve_mapping(table.headers, overrides, kind.fields)
        except (ImportFileError, OSError) as error:
            raise CommandError(str(error)) from error

        self.stdout.write(_("File: %(file)s, %(rows)d rows") % {"file": options["file"], "rows": len(table.rows)})
        self.stdout.write(_("Column mapping:"))
        for import_field in kind.fields:
            index = mapping.get(import_field.key)
            column = f"“{table.headers[index]}”" if index is not None else "–"
            marker = " *" if import_field.required else ""
            self.stdout.write(f"  {import_field.key:<26} {import_field.label + marker:<32} {column}")
        if options["show_mapping"]:
            return

        # The operator on the server may do everything, as the setup command does.
        report = imports.run(kind, table, mapping, dry_run=not options["commit"], user=None, rights=Rights.everything())
        self.stdout.write("")
        for issue in report.warnings:
            self.stdout.write(self.style.WARNING(_("Note: %(issue)s") % {"issue": issue}))
        for issue in report.errors:
            self.stdout.write(self.style.ERROR(_("Error: %(issue)s") % {"issue": issue}))
        if not report.ok:
            raise CommandError(
                ngettext(
                    "%(count)d error. Nothing was imported.",
                    "%(count)d errors. Nothing was imported.",
                    len(report.errors),
                )
                % {"count": len(report.errors)}
            )
        summary = report.as_dict()
        if "items_created" in summary:
            # The material list (IMP-002): models and items; "import_material" reports more.
            self.stdout.write(
                _("Items: %(created)d new, %(updated)d changed, %(unchanged)d unchanged")
                % {
                    "created": report.items_created,
                    "updated": report.items_updated,
                    "unchanged": report.items_unchanged,
                }
            )
        if "created" in summary:
            self.stdout.write(
                _("Records: %(created)d new, %(updated)d changed, %(unchanged)d unchanged")
                % {"created": report.created, "updated": report.updated, "unchanged": report.unchanged}
            )
            for note in report.notes:
                self.stdout.write(f"  {note}")
        if report.dry_run:
            self.stdout.write(self.style.SUCCESS(_("Dry run without errors. Use --commit to import.")))
        else:
            self.stdout.write(self.style.SUCCESS(_("Import completed.")))
