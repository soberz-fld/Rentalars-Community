# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``gateway_link`` module."""

from django.apps import AppConfig


class GatewayLinkConfig(AppConfig):
    """The server's side of the Rentalars Gateway (protocol RGW1)."""

    name = "rentalars.gateway_link"
    label = "gateway_link"
    verbose_name = "Gateway"
