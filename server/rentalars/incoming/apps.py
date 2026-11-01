# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``incoming`` module: incoming invoices in Buchhaltung (DOK-023, DOK-024)."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IncomingConfig(AppConfig):
    """Incoming invoices: upload, reading, note, status, booking in as items with ancillary costs."""

    name = "rentalars.incoming"
    label = "incoming"
    verbose_name = _("Incoming invoices")
