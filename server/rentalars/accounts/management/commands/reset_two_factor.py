# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``reset_two_factor``: switch off two-factor login of a user on the server (AUT-006).

For the case the browser cannot help with: the only administrator lost
phone and recovery codes. Whoever is root on the server may do this::

    sudo rentalars reset_two_factor anna

The user logs in with the password alone afterwards and – if a role or the
setting for administrators requires it – sets two-factor login up again at
once. The security log records the reset.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from rentalars.accounts import twofactor
from rentalars.accounts.models import User


class Command(BaseCommand):
    """Switch two-factor login off for one user."""

    help = "Switches two-factor login off for a user who lost phone and recovery codes."

    def add_arguments(self, parser: CommandParser) -> None:
        """The user name (or e-mail address)."""
        parser.add_argument("username", help="user name or e-mail address")

    def handle(self, *args: Any, **options: Any) -> None:
        """Find the user and reset the second factor."""
        name = options["username"]
        user = User.objects.filter(username__iexact=name).first() or User.objects.filter(email__iexact=name).first()
        if user is None:
            raise CommandError(f"There is no user {name!r}.")
        if not user.has_two_factor:
            self.stdout.write(f"{user.username} does not use two-factor login; nothing to do.")
            return
        twofactor.disable(user)
        self.stdout.write(
            f"Two-factor login of {user.username} is switched off. "
            "If it is required, it is set up again at the next login."
        )
