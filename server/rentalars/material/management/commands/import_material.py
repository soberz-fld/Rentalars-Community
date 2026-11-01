# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``import_material``: take over the existing material list (IMP-007).

Examples::

    # Dry run: check the file and show what would happen. Nothing is written.
    python manage.py import_material bestand.xlsx

    # Really import.
    python manage.py import_material bestand.xlsx --commit

    # A column has an unusual heading: assign it by hand.
    python manage.py import_material bestand.xlsx --map "inventory_number=Inv.-Nr." --map "name=Gerät"

    # Show which columns were recognised, then stop.
    python manage.py import_material bestand.xlsx --show-mapping

    # IMP-014: the prices of the list are gross and include 19 % – they are stored net.
    python manage.py import_material bestand.xlsx --gross --tax-rate 19

    # IMP-011: list the rows that change, each field old → new.
    python manage.py import_material bestand.xlsx --changes
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.material.importer import (
    IMPORT_FIELDS,
    ImportFileError,
    import_material,
    read_table,
    resolve_mapping,
)
from rentalars.material.numbering import format_inventory_number


class Command(BaseCommand):
    """Reads an XLSX or CSV file and creates categories, suppliers, models and items.

    Without ``--commit`` the command only performs a dry run: it checks every
    row and reports what the import would do, but writes nothing (IMP-009).
    """

    help = (
        "Imports the material table (XLSX or CSV). Without --commit only a dry run is made, "
        "which writes nothing and reports all errors with their row number."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("file", help="path of the XLSX or CSV file")
        parser.add_argument("--commit", action="store_true", help="really import (default: dry run)")
        parser.add_argument("--sheet", help="name of the worksheet (default: the first)")
        parser.add_argument(
            "--map",
            action="append",
            default=[],
            metavar="FIELD=COLUMN",
            help='assign a column by hand, e.g. --map "name=Gerät"; an empty column skips the field',
        )
        parser.add_argument("--show-mapping", action="store_true", help="only show the recognised column mapping")
        parser.add_argument(
            "--gross", action="store_true", help="the purchase prices are gross; they are stored net (IMP-014)"
        )
        parser.add_argument(
            "--tax-rate",
            help="the tax rate in percent that gross prices include (default: the default tax rate)",
        )
        parser.add_argument(
            "--changes", action="store_true", help="list the rows that change, each field old → new (IMP-011)"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the import or the dry run and print the report."""
        overrides: dict[str, str] = {}
        for assignment in options["map"]:
            if "=" not in assignment:
                raise CommandError(_("--map expects FIELD=COLUMN, not: %(value)s") % {"value": assignment})
            key, column = assignment.split("=", 1)
            overrides[key.strip()] = column.strip()

        try:
            table = read_table(options["file"], sheet=options["sheet"])
            mapping = resolve_mapping(table.headers, overrides)
        except (ImportFileError, OSError) as error:
            raise CommandError(str(error)) from error

        self.stdout.write(_("File: %(file)s, %(rows)d rows") % {"file": options["file"], "rows": len(table.rows)})
        self.stdout.write(_("Column mapping:"))
        for import_field in IMPORT_FIELDS:
            index = mapping.get(import_field.key)
            column = f"“{table.headers[index]}”" if index is not None else "–"
            marker = " *" if import_field.required else ""
            self.stdout.write(f"  {import_field.key:<24} {import_field.label + marker:<32} {column}")
        if options["show_mapping"]:
            return

        gross_rate = None
        if options["gross"]:
            from decimal import Decimal, InvalidOperation

            from rentalars.material.importer import default_tax_rate

            try:
                gross_rate = Decimal(str(options["tax_rate"] or default_tax_rate()).replace(",", "."))
            except InvalidOperation as error:
                raise CommandError(_("--tax-rate expects a percentage such as 19.")) from error
            self.stdout.write(_("Gross prices with %(rate)s %% tax are stored net.") % {"rate": gross_rate})
        report = import_material(
            table, mapping, dry_run=not options["commit"], actor="system:import", gross_rate=gross_rate
        )

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

        self.stdout.write(
            _("Material models: %(created)d new, %(updated)d changed")
            % {"created": report.models_created, "updated": report.models_updated}
        )
        self.stdout.write(
            _("Items: %(created)d new, %(updated)d changed, %(unchanged)d unchanged")
            % {"created": report.items_created, "updated": report.items_updated, "unchanged": report.items_unchanged}
        )
        if report.items_flagged:
            self.stdout.write(
                ngettext(
                    "%(count)d item with the status “import error”: what could not be taken over is in its "
                    "notes. Fill in the fields by hand and choose another status.",
                    "%(count)d items with the status “import error”: what could not be taken over is in their "
                    "notes. Fill in the fields by hand and choose another status.",
                    report.items_flagged,
                )
                % {"count": report.items_flagged}
            )
        if report.categories_created:
            self.stdout.write(
                _("New categories (check the codes): %(names)s") % {"names": ", ".join(report.categories_created)}
            )
        if report.suppliers_created:
            self.stdout.write(_("New suppliers: %(names)s") % {"names": ", ".join(report.suppliers_created)})
        if report.purchase_sets:
            self.stdout.write(_("Bought as sets (the item with the price first):"))
            for line in report.purchase_sets:
                self.stdout.write(f"  {line}")
        if report.installed_links:
            self.stdout.write(
                ngettext(
                    "%(count)d item linked as “permanently installed” (switch it to “loosely contained” where needed):",
                    "%(count)d items linked as “permanently installed” (switch single ones to “loosely contained” where needed):",
                    len(report.installed_links),
                )
                % {"count": len(report.installed_links)}
            )
            for link in report.installed_links:
                self.stdout.write(f"  {link}")
        if options["changes"]:
            self._print_changes(report.as_dict()["rows"])
        self.stdout.write(
            _("Highest ID: %(highest)s, next new ID: %(next)s")
            % {"highest": format_inventory_number(report.highest_id), "next": report.next_id}
        )
        if report.dry_run:
            self.stdout.write(self.style.SUCCESS(_("Dry run without errors. Use --commit to import.")))
        else:
            self.stdout.write(self.style.SUCCESS(_("Import completed.")))

    def _print_changes(self, rows: list[dict[str, Any]]) -> None:
        """IMP-011: one line per changed row – "Row 5, 0310 Funkempfänger: Serial number: A → B"."""
        changed = [row for row in rows if row["status"] == "changed"]
        self.stdout.write(_("Changed rows: %(count)d") % {"count": len(changed)})
        for row in changed:
            fields = "; ".join(
                f"{change['label']}: {change['old']} → {change['new']}" if not change.get("hidden") else change["label"]
                for change in row["changes"]
            )
            notes = "; ".join(row["notes"])
            details = "; ".join(part for part in (fields, notes) if part)
            self.stdout.write(f"  {_('Row %(row)s') % {'row': row['row']}}, {row['label']}: {details}")
