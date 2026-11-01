# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``prepare_setup``: protect the first-run setup with a one-time link (NFA-033).

The installation script runs this command and shows the printed address. Only
whoever has that address can complete the setup and thereby create the first
administrator.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from rentalars.core.models import SystemSettings


class Command(BaseCommand):
    """Creates a new setup token and prints the address of the setup page."""

    help = "Prints the one-time address for the first-run setup in the browser."

    def handle(self, *args: Any, **options: Any) -> None:
        """Print the setup address, or say that the setup is already done."""
        system_settings = SystemSettings.load()
        if system_settings.setup_completed:
            self.stdout.write(_("The first-run setup is already completed."))
            return
        token = system_settings.new_setup_token()
        self.stdout.write(f"{settings.RENTALARS_URL}/setup/?token={token}")
