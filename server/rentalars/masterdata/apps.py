# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``masterdata`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MasterdataConfig(AppConfig):
    """Categories, units, tax rates, rental scales and other reference lists (ADM-002)."""

    name = "rentalars.masterdata"
    label = "masterdata"
    verbose_name = _("Master data")
