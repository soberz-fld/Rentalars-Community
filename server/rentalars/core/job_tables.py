# SPDX-License-Identifier: GPL-3.0-or-later
"""The own tasks in the background as a table: columns, sorting, groups and CSV (NFA-041, UIX-040)."""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from rentalars.core.tables import Column, TableDefinition, date_text, grouped_by_day, link

JOB_TABLE = TableDefinition(
    "background_jobs",
    [
        Column(
            "task",
            _("Task"),
            cell=lambda job: link(reverse("core:job", args=[job.pk]), job.title),
            text=lambda job: job.title,
            sort=("title", "-created_at"),
            fixed=True,
            group="title",  # UIX-044: every column groups, a moment by its day
        ),
        Column(
            "started",
            _("Started"),
            cell=lambda job: date_text(job.created_at),
            text=lambda job: job.created_at,
            sort="created_at",
            css="nowrap",
            **grouped_by_day("created_at"),
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda job: job.get_status_display(),
            sort=("status", "-created_at"),
            group="status",
        ),
        Column(
            "finished",
            _("Finished"),
            cell=lambda job: date_text(job.finished_at),
            text=lambda job: job.finished_at,
            sort="finished_at",
            css="nowrap",
            default=False,
            **grouped_by_day("finished_at"),
        ),
        Column(
            "message",
            _("Message"),
            cell=lambda job: job.message,
            sort=("message", "-created_at"),
            default=False,
            group="message",
        ),
    ],
    default_sort="-started",
)
