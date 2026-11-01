# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``mail`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MailConfig(AppConfig):
    """E-mails of projects: fetching, assigning by tag, sending (chapter 5.15)."""

    name = "rentalars.mail"
    label = "mail"
    verbose_name = _("E-mail")
