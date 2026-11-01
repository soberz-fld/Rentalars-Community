# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``customers`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CustomersConfig(AppConfig):
    """Customers and their contacts (chapter 5.4)."""

    name = "rentalars.customers"
    label = "customers"
    verbose_name = _("Customers")

    def ready(self) -> None:
        """Make the import of this module known (IMP-001)."""
        from rentalars.accounts.rights import Module
        from rentalars.core import import_exports, imports
        from rentalars.customers import import_export, importer

        import_exports.register(import_export.EXPORT)  # IMP-017: the export in the format of the import
        imports.register(
            imports.ImportKind(
                key="customers",
                title=importer.TITLE,
                module=Module.CUSTOMERS,
                fields=importer.IMPORT_FIELDS,
                run=importer.run_import,
                introduction=importer.INTRODUCTION,
                list_url="customers:list",
                # IMP-013: the report names the outcome of every row.
                report_template="customers/_import_report.html",
            )
        )
