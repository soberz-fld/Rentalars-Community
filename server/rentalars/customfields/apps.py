# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``customfields`` module (MAT-071, MAT-072, MAT-073)."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CustomFieldsConfig(AppConfig):
    """Custom fields of material items: definitions, fieldsets and the values of every item (MAT-071, MAT-072, MAT-073)."""

    name = "rentalars.customfields"
    label = "customfields"
    verbose_name = _("Custom fields")

    def ready(self) -> None:
        """The custom fields marked "in lists" become choosable columns of the item list (MAT-073)."""
        from rentalars.customfields.tables import list_columns, prepare_list_values
        from rentalars.material.tables import ITEM_TABLE

        ITEM_TABLE.add_column_source(list_columns, prepare=prepare_list_values)
