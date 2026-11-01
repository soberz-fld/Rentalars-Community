# SPDX-License-Identifier: GPL-3.0-or-later
"""The top-level address table: which path belongs to which module."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

#: A clear page for "Bad Request", above all for a host name the application does not answer to.
handler400 = "rentalars.core.errors.bad_request"

urlpatterns = [
    path("", include("rentalars.core.urls")),
    path("", include("rentalars.accounts.urls")),
    path("", include("rentalars.material.urls")),
    path("", include("rentalars.products.urls")),
    path("", include("rentalars.customers.urls")),
    path("", include("rentalars.personnel.urls")),
    path("", include("rentalars.projects.urls")),
    path("", include("rentalars.timetracking.urls")),
    path("", include("rentalars.packing.urls")),
    path("", include("rentalars.documents.urls")),
    path("", include("rentalars.incoming.urls")),  # Incoming invoices
    path("", include("rentalars.availability.urls")),
    path("", include("rentalars.mail.urls")),
    path("", include("rentalars.notifications.urls")),
    path("", include("rentalars.schedule.urls")),
    path("", include("rentalars.chat.urls")),  # UIX-010
    path("", include("rentalars.ai.urls")),  # EML-040, EML-044, ADM-017
    path("administration/automations/", include("rentalars.automations.urls")),  # ADM-013
    path("administration/custom-fields/", include("rentalars.customfields.urls")),  # MAT-071, MAT-072
    path("api/v1/", include("rentalars.api.urls")),
    path("administration/webhooks/", include("rentalars.api.webhook_urls")),  # API-012
    path("administration/gateway/", include("rentalars.gateway_link.urls")),  # GWL-011
    # Master data is maintained in Django's administration interface (ADM-007).
    path("administration/masterdata/", admin.site.urls),
]
