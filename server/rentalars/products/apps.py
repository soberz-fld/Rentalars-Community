# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``products`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProductsConfig(AppConfig):
    """Products, kits and article numbers (chapter 5.3)."""

    name = "rentalars.products"
    label = "products"
    verbose_name = _("Products")

    def ready(self) -> None:
        """Make the import of this module known (IMP-001)."""
        from rentalars.accounts.rights import Module
        from rentalars.core import import_exports, imports
        from rentalars.products import import_export, importer

        import_exports.register(import_export.EXPORT)  # IMP-017: the export in the format of the import
        imports.register(
            imports.ImportKind(
                key="products",
                title=importer.TITLE,
                module=Module.PRODUCTS,
                fields=importer.IMPORT_FIELDS,
                run=importer.run_import,
                introduction=importer.INTRODUCTION,
                list_url="products:list",
                head_template="material/_import_head.html",
            )
        )
