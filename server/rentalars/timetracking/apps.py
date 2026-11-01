# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``timetracking`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TimeTrackingConfig(AppConfig):
    """Recording hours, approving them, reports (chapter 5.9)."""

    name = "rentalars.timetracking"
    label = "timetracking"
    verbose_name = _("Time tracking")
