# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the products module."""

from django.urls import path

from rentalars.products import relation_views, suggestion_views, views

app_name = "products"

urlpatterns = [
    path("products/", views.product_list, name="list"),
    path("products/suggest/", views.product_suggest, name="suggest"),
    path("products/new/", views.product_edit, name="create"),
    # The rental scales are master data of the settings (UIX-013); their pages live there too (NFA-074).
    path("administration/scales/", views.scale_list, name="scale_list"),
    path("administration/scales/new/", views.scale_edit, name="scale_create"),
    path("administration/scales/<int:pk>/", views.scale_edit, name="scale_edit"),
    path("products/<product:pk>/", views.product_detail, name="detail"),
    path("products/<product:pk>/edit/", views.product_edit, name="edit"),
    # PRD-049: the article number for the category chosen in the form of an existing product (htmx).
    path("products/<product:pk>/article-number/", views.article_number_field, name="article_number"),
    path("products/<product:pk>/timeline/", views.product_timeline, name="timeline"),
    path("products/<product:pk>/active/", views.product_set_active, name="set_active"),
    path("products/<product:pk>/take-over-changes/", views.product_take_over_changes, name="take_over_changes"),
    path("products/<product:pk>/delete/", views.product_delete, name="delete"),
    path("products/<product:pk>/components/", views.component_add, name="component_add"),
    path(
        "products/<product:pk>/components/<int:component_pk>/remove/", views.component_remove, name="component_remove"
    ),
    # Accessory and replacement suggestions; PRD-023, VFG-015: the relations of a product.
    path("products/<product:pk>/relations/add/", relation_views.relation_add, name="relation_add"),
    path("products/<product:pk>/relations/<int:relation_pk>/", relation_views.relation_update, name="relation_update"),
    path(
        "products/<product:pk>/relations/<int:relation_pk>/move/<str:direction>/",
        relation_views.relation_move,
        name="relation_move",
    ),
    path(
        "products/<product:pk>/relations/<int:relation_pk>/delete/",
        relation_views.relation_delete,
        name="relation_delete",
    ),
    # The suggestions in the planning of a project (hint, accept, dismiss, bring back).
    path("projects/<project:pk>/suggestions/", suggestion_views.suggestions_panel, name="suggestions_panel"),
    path(
        "projects/<project:pk>/suggestions/<int:relation_pk>/add/",
        suggestion_views.suggestion_accept,
        name="suggestion_accept",
    ),
    path("projects/<project:pk>/suggestions/dismiss/", suggestion_views.suggestion_dismiss, name="suggestion_dismiss"),
    path("projects/<project:pk>/suggestions/restore/", suggestion_views.suggestion_restore, name="suggestion_restore"),
]
