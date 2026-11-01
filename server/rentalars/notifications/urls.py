# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the notifications."""

from django.urls import path

from rentalars.notifications import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.notification_list, name="list"),
    path("notifications/<int:pk>/", views.notification_open, name="open"),
    path("notifications/read/", views.mark_all_read, name="mark_all_read"),
    path("account/notifications/", views.preferences, name="preferences"),
    # VFG-036: Einstellungen → Benachrichtigungen – when and how far ahead shortages are reported.
    path("administration/notifications/", views.company_settings, name="company_settings"),
]
