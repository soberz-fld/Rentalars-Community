# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``automations`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AutomationsConfig(AppConfig):
    """Automations with triggers, defined under Einstellungen → Automationen (ADM-013)."""

    name = "rentalars.automations"
    label = "automations"
    verbose_name = _("Automations")

    def ready(self) -> None:
        """ADM-013: a project reaching a status and an answer to a deployment request are noticed by signals."""
        from rentalars.automations.signals import connect_signals

        connect_signals()
