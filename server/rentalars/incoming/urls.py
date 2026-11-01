# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the incoming invoices (DOK-023, DOK-024): Buchhaltung → Eingangsrechnungen and the settings."""

from django.urls import path

from rentalars.incoming import payment_views, views

app_name = "incoming"

urlpatterns = [
    path("accounting/incoming/", views.invoice_list, name="list"),
    path("accounting/incoming/capture/", views.invoice_capture, name="capture"),
    path("accounting/incoming/from-purchase/", views.invoice_from_purchase, name="from_purchase"),
    path("accounting/incoming/upload/", views.invoice_upload, name="upload"),
    path("accounting/incoming/<int:pk>/", views.invoice_detail, name="detail"),
    path("accounting/incoming/<int:pk>/file/", views.invoice_file, name="file"),
    path("accounting/incoming/<int:pk>/xml/", views.invoice_xml, name="xml"),
    path("accounting/incoming/<int:pk>/reading/", views.invoice_reading, name="reading"),
    path("accounting/incoming/<int:pk>/read/", views.invoice_read, name="read"),
    path("accounting/incoming/<int:pk>/supplier/", views.invoice_create_supplier, name="create_supplier"),
    path("accounting/incoming/<int:pk>/status/", views.invoice_status, name="status"),
    path("accounting/incoming/<int:pk>/delete/", views.invoice_delete, name="delete"),
    path("accounting/incoming/<int:pk>/costing/", views.invoice_costing, name="costing"),
    path("accounting/incoming/<int:pk>/kontierung-sum/", views.kontierung_sum, name="kontierung_sum"),
    path("accounting/incoming/<int:pk>/book/", views.invoice_book, name="book"),
    # DOK-048, DOK-042: the payments of an invoice and the check of its e-invoice.
    path("accounting/incoming/<int:pk>/payments/", payment_views.invoice_payments, name="payments"),
    path("accounting/incoming/<int:pk>/check/", payment_views.invoice_check, name="check"),
    path("administration/incoming-invoices/", views.settings_page, name="settings"),
]
