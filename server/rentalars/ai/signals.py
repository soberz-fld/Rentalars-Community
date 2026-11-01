# SPDX-License-Identifier: GPL-3.0-or-later
"""Forgetting a summary whose mails are gone (EML-040, EML-031; and its earlier versions).

A summary carries the content of the mails it covers. When one of them is
deleted – by hand, after the retention period, or because a customer is
anonymised – the summary of its project (and of the whole project above a
part) goes as well, if it was made after the mail arrived.
"""

from __future__ import annotations

from typing import Any

from rentalars.ai.models import AISummary, AISummaryVersion


def mail_deleted(sender: Any, instance: Any, **kwargs: Any) -> None:
    """``post_delete`` of a project mail: delete the summaries that may contain it."""
    from rentalars.projects.models import Project

    project_id = instance.project_id
    parent_id = Project.objects.filter(pk=project_id).values_list("parent_id", flat=True).first()
    candidates = AISummary.objects.filter(
        project_id__in=[pk for pk in (project_id, parent_id) if pk], created_at__gte=instance.imported_at
    )
    for summary in candidates:
        if project_id in (summary.covered_projects or [summary.project_id]):
            summary.delete()
    # The earlier versions carry the content of the mail as well.
    versions = AISummaryVersion.objects.filter(
        project_id__in=[pk for pk in (project_id, parent_id) if pk], created_at__gte=instance.imported_at
    )
    for version in versions:
        if project_id in (version.covered_projects or [version.project_id]):
            version.delete()


def chat_message_deleted(sender: Any, instance: Any, **kwargs: Any) -> None:
    """``post_delete`` of a chat message: delete the summaries that read the chat after it was written.

    Only summaries made with the chat can hold its content. The earlier versions go with them.
    """
    from rentalars.projects.models import Project

    project_id = instance.project_id
    parent_id = Project.objects.filter(pk=project_id).values_list("parent_id", flat=True).first()
    ids = [pk for pk in (project_id, parent_id) if pk]
    for model in (AISummary, AISummaryVersion):
        for row in model.objects.filter(project_id__in=ids, include_chat=True, created_at__gte=instance.created_at):
            if project_id in (row.covered_projects or [row.project_id]):
                row.delete()
