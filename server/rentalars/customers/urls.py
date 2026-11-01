# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the customers module."""

from django.urls import path

from rentalars.customers import views

app_name = "customers"

urlpatterns = [
    path("customers/", views.customer_list, name="list"),
    path("customers/suggest/", views.customer_suggest, name="suggest"),
    path("customers/quick-new/", views.customer_quick_create, name="quick_create"),  # PRJ-070
    path("customers/duplicates/", views.customer_duplicates, name="duplicates"),
    path("customers/new/", views.customer_edit, name="create"),
    path("customers/<int:pk>/", views.customer_detail, name="detail"),
    path("customers/<int:pk>/edit/", views.customer_edit, name="edit"),
    path("customers/<int:pk>/delete/", views.customer_delete, name="delete"),
    path("customers/<int:pk>/anonymise/", views.customer_anonymise, name="anonymise"),
    path("customers/<int:pk>/export/", views.customer_export, name="export"),
    path("customers/contacts/greeting/", views.contact_greeting_preview, name="greeting_preview"),
    path("customers/<int:customer_pk>/contacts/new/", views.contact_edit, name="contact_create"),
    path(
        "customers/<int:customer_pk>/contacts/quick-new/", views.contact_quick_create, name="contact_quick_create"
    ),  # PRJ-140
    path("customers/<int:customer_pk>/contacts/<int:pk>/", views.contact_edit, name="contact_edit"),
    path("customers/<int:customer_pk>/contacts/<int:pk>/delete/", views.contact_delete, name="contact_delete"),
    # KND-005: further billing and delivery addresses.
    path("customers/<int:customer_pk>/addresses/new/", views.address_edit, name="address_create"),
    path("customers/<int:customer_pk>/addresses/<int:pk>/", views.address_edit, name="address_edit"),
    path("customers/<int:customer_pk>/addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    # KND-009: venues as master data of their own.
    path("customers/venues/", views.venue_list, name="venue_list"),
    path("customers/venues/new/", views.venue_edit, name="venue_create"),
    path("customers/venues/suggest/", views.venue_suggest, name="venue_suggest"),
    path("customers/venues/quick-new/", views.venue_quick_create, name="venue_quick_create"),
    path("customers/venues/<int:pk>/", views.venue_detail, name="venue_detail"),
    path("customers/venues/<int:pk>/edit/", views.venue_edit, name="venue_edit"),
    path("customers/venues/<int:pk>/delete/", views.venue_delete, name="venue_delete"),
    path("customers/venues/<int:pk>/hall-plan/", views.venue_hall_plan, name="venue_hall_plan"),
]
