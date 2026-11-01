# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the availability module."""

from django.urls import path

from rentalars.availability import views

app_name = "availability"

urlpatterns = [
    path("shortages/", views.shortages, name="shortages"),
]
