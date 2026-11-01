# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the packing module.

The first packlist of a project keeps its short address ``/projects/<id>/packlist/``; further
packlists (PCK-008) live under ``/projects/<id>/packlists/<packlist>/``.
"""

from django.urls import path

from rentalars.packing import views

app_name = "packing"

urlpatterns = [
    path("projects/<project:pk>/packlist/", views.packlist, name="packlist"),
    path("projects/<project:pk>/packlist/pdf/", views.packlist_pdf, name="pdf"),
    path("projects/<project:pk>/packlist/row/", views.packlist_row, name="row"),
    path("projects/<project:pk>/packlist/items/", views.packlist_items, name="items"),
    # PRJ-048: the whole project with all its subprojects, read-only.
    path("projects/<project:pk>/packlist/family/", views.family_packlist, name="family"),
    path("projects/<project:pk>/packlist/family/pdf/", views.family_packlist_pdf, name="family_pdf"),
    path("projects/<project:pk>/packlist/<slug:action>/", views.packlist_action, name="action"),
    path("projects/<project:pk>/packlists/new/", views.packlist_create, name="packlist_create"),
    path("projects/<project:pk>/packlists/lines/", views.packlist_lines, name="packlist_lines"),
    path("projects/<project:pk>/packlists/<int:packlist_pk>/", views.packlist, name="packlist_detail"),
    path("projects/<project:pk>/packlists/<int:packlist_pk>/pdf/", views.packlist_pdf, name="packlist_pdf"),
    path("projects/<project:pk>/packlists/<int:packlist_pk>/row/", views.packlist_row, name="packlist_row"),
    path("projects/<project:pk>/packlists/<int:packlist_pk>/items/", views.packlist_items, name="packlist_items"),
    path(
        "projects/<project:pk>/packlists/<int:packlist_pk>/<slug:action>/",
        views.packlist_action,
        name="packlist_action",
    ),
    path("material/items/<int:item_pk>/extract/", views.extract, name="extract"),
    path("packing/extractions/<int:pk>/cancel/", views.extraction_cancel, name="extraction_cancel"),
]
