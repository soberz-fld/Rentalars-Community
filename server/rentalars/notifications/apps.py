# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``notifications`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotificationsConfig(AppConfig):
    """Notifications in the application and by e-mail (UIX-005)."""

    name = "rentalars.notifications"
    label = "notifications"
    verbose_name = _("Notifications")
