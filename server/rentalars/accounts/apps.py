# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``accounts`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    """Users, roles, rights, API tokens and login protection (chapter 5.1)."""

    name = "rentalars.accounts"
    label = "accounts"
    verbose_name = _("Users and rights")

    def ready(self) -> None:
        """Connect the signals that note logins and logouts (AUT-008, AUT-022) and changed addresses (AUT-030)."""
        from rentalars.accounts import (
            notices,
            sessions,  # noqa: F401 - registers the signal receivers
        )

        notices.connect()
