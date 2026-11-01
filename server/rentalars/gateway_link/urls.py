# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the gateway page in the settings (GWL-011)."""

from django.urls import path

from rentalars.gateway_link import web

app_name = "gateway"

urlpatterns = [
    path("", web.gateway_page, name="page"),
    path("devices/<str:device_id>/revoke/", web.revoke, name="revoke"),
]
