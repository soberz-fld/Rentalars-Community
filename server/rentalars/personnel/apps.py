# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``personnel`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PersonnelConfig(AppConfig):
    """People, job functions, hourly rates, absences (chapter 5.5)."""

    name = "rentalars.personnel"
    label = "personnel"
    verbose_name = _("Personnel")

    def ready(self) -> None:
        """Make the import of this module known (IMP-001)."""
        from rentalars.accounts.rights import Module
        from rentalars.core import import_exports, imports
        from rentalars.personnel import import_export, importer

        import_exports.register(import_export.EXPORT)  # IMP-017: the export in the format of the import
        imports.register(
            imports.ImportKind(
                key="people",
                title=importer.TITLE,
                module=Module.PERSONNEL,
                fields=importer.IMPORT_FIELDS,
                run=importer.run_import,
                introduction=importer.INTRODUCTION,
                list_url="personnel:person_list",
            )
        )
        # PER-023: a changed crew line makes its person's CalDAV calendar due.
        from rentalars.personnel.calendars import connect_signals

        connect_signals()
