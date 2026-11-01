# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``availability`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AvailabilityConfig(AppConfig):
    """The availability calculation (chapter 5.7). Has no tables of its own."""

    name = "rentalars.availability"
    label = "availability"
    verbose_name = _("Availability")
