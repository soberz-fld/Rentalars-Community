# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``schedule`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ScheduleConfig(AppConfig):
    """Calendar, timelines and the personnel plan (PRJ-028, VFG-012, VFG-014); the calendar links (VFG-040)."""

    name = "rentalars.schedule"
    label = "schedule"
    verbose_name = _("Planning")

    def ready(self) -> None:
        """A product or item going out of use ends its calendar link (VFG-040)."""
        from rentalars.schedule.calendar_links import connect_signals

        connect_signals()
