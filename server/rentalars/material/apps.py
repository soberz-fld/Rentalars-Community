# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``material`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MaterialConfig(AppConfig):
    """Material models and material items (chapter 5.2)."""

    name = "rentalars.material"
    label = "material"
    verbose_name = _("Material")

    def ready(self) -> None:
        """Make the background tasks and the import of this module known (NFA-041, IMP-001)."""
        from django.db.models.signals import post_delete, pre_delete

        from rentalars.accounts.rights import Module
        from rentalars.core import import_exports, imports
        from rentalars.core.jobs import register
        from rentalars.material import import_export, importer, services
        from rentalars.material.models import MaterialFile, MaterialItem, MaterialModel

        register("labels", "rentalars.material.labels:run_job")
        # MAT-090: a photo goes from the disk with its row – also when the item or model goes with all its files.
        post_delete.connect(services.file_row_deleted, sender=MaterialFile, dispatch_uid="material.file_row_deleted")
        # Where the database cannot defer checks (MySQL, MariaDB), Django empties the nullable owner of a file before it
        # deletes the file – which the rule "exactly one owner" forbids. So the files go first (found on MariaDB).
        for owner in (MaterialItem, MaterialModel):
            pre_delete.connect(
                services.files_before_owner,
                sender=owner,
                dispatch_uid=f"material.files_before_{owner.__name__}",
            )
        import_exports.register(import_export.EXPORT)  # IMP-017: the export in the format of the import
        import_exports.register_columns("material", import_export.CUSTOM_FIELDS)  # MAT-073: the custom fields
        imports.register(
            imports.ImportKind(
                key="material",
                title=_("Import material"),
                module=Module.MATERIAL,
                fields=importer.IMPORT_FIELDS,
                run=importer.run_import,
                introduction=_(
                    "The file needs one row per item and a heading row. The 13 columns of the material list are "
                    "recognised by their headings; you can correct the assignment in the next step."
                ),
                list_url="material:item_list",
                command="rentalars import_material",
                report_template="material/_import_report.html",
                head_template="material/_import_head.html",
                # IMP-014: are the prices of the file net or gross – and which tax rate do gross ones include?
                options=(
                    imports.ImportOption(
                        "prices",
                        _("The purchase prices of the file are"),
                        [
                            (importer.PRICES_NET, _("net – stored as they are")),
                            (importer.PRICES_GROSS, _("gross – the tax is taken out")),
                        ],
                        default=importer.PRICES_NET,
                        help_text=_(
                            "Rentalars keeps purchase prices net. A price cell like #0851 means: bought as a set, "
                            "the price is noted at 0851."
                        ),
                    ),
                    imports.ImportOption(
                        "price_tax_rate",
                        _("Gross prices include"),
                        importer.tax_rate_choices,
                        default=importer.default_tax_rate,
                        help_text=_("Only for gross prices."),
                    ),
                ),
            )
        )
