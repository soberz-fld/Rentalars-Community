# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the webhook pages in the settings (API-012), below ``/administration/webhooks/``."""

from __future__ import annotations

from django.urls import path

from rentalars.api import webhook_views as views

app_name = "webhooks"

urlpatterns = [
    path("", views.webhook_list, name="list"),
    path("new/", views.webhook_edit, name="create"),
    path("<int:pk>/", views.webhook_detail, name="detail"),
    path("<int:pk>/edit/", views.webhook_edit, name="edit"),
    path("<int:pk>/delete/", views.webhook_delete, name="delete"),
    path("<int:pk>/secret/", views.webhook_secret, name="secret"),
    path("<int:pk>/test/", views.webhook_test, name="test"),
    path("<int:pk>/deliveries/<int:delivery_pk>/redeliver/", views.webhook_redeliver, name="redeliver"),
]
