# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of Einstellungen → Eigene Felder and Feldsätze (MAT-071, MAT-072), below ``/administration/custom-fields/``."""

from django.urls import path

from rentalars.customfields import views

app_name = "customfields"

urlpatterns = [
    path("", views.field_list, name="field_list"),
    path("new/", views.field_edit, name="field_create"),
    path("<int:pk>/", views.field_edit, name="field_edit"),
    path("<int:pk>/delete/", views.field_delete, name="field_delete"),
    path("fieldsets/", views.fieldset_list, name="fieldset_list"),
    path("fieldsets/new/", views.fieldset_edit, name="fieldset_create"),
    path("fieldsets/<int:pk>/", views.fieldset_edit, name="fieldset_edit"),
    path("fieldsets/<int:pk>/delete/", views.fieldset_delete, name="fieldset_delete"),
]
