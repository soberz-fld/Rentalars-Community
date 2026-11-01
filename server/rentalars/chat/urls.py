# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the chat of a project (UIX-010)."""

from django.urls import path

from rentalars.chat import views

app_name = "chat"

urlpatterns = [
    path("projects/<project:pk>/chat/", views.chat_page, name="project"),
    path("projects/<project:pk>/chat/messages/", views.chat_messages, name="messages"),
    path("projects/<project:pk>/chat/<int:message_pk>/edit/", views.message_edit, name="edit"),
    path("projects/<project:pk>/chat/<int:message_pk>/delete/", views.message_delete, name="delete"),
    # UIX-049: a photo or video, and its preview.
    path("projects/<project:project_pk>/chat/media/<int:pk>/", views.media_file, name="media"),
    path(
        "projects/<project:project_pk>/chat/media/<int:pk>/small/",
        views.media_file,
        {"small": True},
        name="media_small",
    ),
]
