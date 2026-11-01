# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``create_demo_data``: fill an empty installation with sample data (NFA-017)."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from rentalars.core.demo import create_demo_data


class Command(BaseCommand):
    """Creates products, material, customers and projects to try things out."""

    help = "Creates sample data in an installation that has no data of its own yet."

    def handle(self, *args: Any, **options: Any) -> None:
        """Create the data and say what happened."""
        if create_demo_data():
            self.stdout.write(self.style.SUCCESS(_("Sample data created.")))
        else:
            self.stdout.write(_("This installation already has data; nothing was created."))
