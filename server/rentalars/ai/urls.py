# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the AI module (EML-040, EML-044, ADM-017)."""

from django.urls import path

from rentalars.ai import views

app_name = "ai"

urlpatterns = [
    # Einstellungen → KI.
    path("administration/ai/", views.settings_page, name="settings"),
    path("administration/ai/local/summaries/", views.local_summaries, name="local_summaries"),
    path("administration/ai/local/speed-test/", views.local_speed_test, name="local_speed_test"),
    path("administration/ai/providers/new/", views.provider_edit, name="provider_create"),
    path("administration/ai/providers/<int:provider_pk>/", views.provider_edit, name="provider_edit"),
    path("administration/ai/providers/<int:provider_pk>/delete/", views.provider_delete, name="provider_delete"),
    path("administration/ai/providers/<int:provider_pk>/check/", views.provider_check, name="provider_check"),
    path("administration/ai/calls/", views.call_log, name="calls"),
    # The automatic summaries – opt in, caps, data classes, the runs.
    path("administration/ai/automatic/", views.auto_settings, name="auto_settings"),
    path("administration/ai/automatic/preview/", views.auto_preview, name="auto_preview"),
    path("administration/ai/automatic/run/", views.auto_run_now, name="auto_run"),
    # The correspondence of a project or service case: overview and summary; the reply draft.
    path("projects/<project:pk>/mails/summary/", views.summary_block, name="summary"),
    path("projects/<project:pk>/mails/summary/automatic/", views.auto_switch_project, name="auto_project"),
    path(
        "projects/<project:project_pk>/mails/summary/automatic/customer/<int:pk>/",
        views.auto_switch_customer,
        name="auto_customer",
    ),
    path("projects/<project:pk>/mails/draft/", views.draft_start, name="draft"),
    path("projects/<project:pk>/mails/draft/<int:job_pk>/", views.draft_job, name="draft_job"),
]
