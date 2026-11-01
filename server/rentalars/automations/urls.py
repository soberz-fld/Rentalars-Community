# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of Einstellungen → Automationen (ADM-013), below ``/administration/automations/``."""

from django.urls import path

from rentalars.automations import views

app_name = "automations"

urlpatterns = [
    path("", views.automation_list, name="list"),
    path("new/", views.automation_edit, name="create"),
    path("restore-defaults/", views.automation_restore_defaults, name="restore_defaults"),  # ADM-019
    path("<int:pk>/", views.automation_edit, name="edit"),
    path("<int:pk>/delete/", views.automation_delete, name="delete"),
    path("<int:pk>/toggle/", views.automation_toggle, name="toggle"),
]
