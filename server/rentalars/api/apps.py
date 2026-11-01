# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``api`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ApiConfig(AppConfig):
    """Shared plumbing of the HTTP API: errors, paging, rights, routing (chapter 5.13), and webhooks (API-012)."""

    name = "rentalars.api"
    label = "api"
    verbose_name = _("API")

    def ready(self) -> None:
        """API-012: a new project, a changed project status and a stored document are events for webhooks."""
        from rentalars.api.webhooks import connect_signals

        connect_signals()
