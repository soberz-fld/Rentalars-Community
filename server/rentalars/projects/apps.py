# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``projects`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProjectsConfig(AppConfig):
    """Projects, groups, material lines and price calculation (chapter 5.6)."""

    name = "rentalars.projects"
    label = "projects"
    verbose_name = _("Projects")

    def ready(self) -> None:
        """Make the background task of the legacy import known and watch the products."""
        from rentalars.core.jobs import register

        register("legacy_invoices", "rentalars.ai.legacy_invoices:run_job")
        from rentalars.projects import product_notice

        product_notice.connect()  # PRJ-072: tell the projects when a planned product was changed
