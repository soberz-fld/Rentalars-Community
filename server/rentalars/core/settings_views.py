# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the settings for data protection and operation: access log, backup and encryption.

* **Access log** (AUT-028): who read which record – with filters and CSV.
* **Backup and encryption** (ADM-009, ADM-010): a backup made in the browser
  for download, and where encryption stands and how it is switched on.
* **Readable export of all data** (IMP-006): a section of the
  same page, with what tells it from a backup.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core import access_log, backup
from rentalars.core.listing import end_of_day, paginate, start_of_day
from rentalars.core.models import AccessAction, AccessKind, AccessLogEntry, BackgroundJob, SystemSettings


@module_required(Module.ADMINISTRATION)
def access_log_page(request: HttpRequest) -> HttpResponse:
    """The access log: who opened, downloaded or exported which record, and when (AUT-028).

    Filters: user, kind of object, one object (``type`` and ``object`` – the
    link on every entry sets them), kind of access, period and a text. The
    filtered view is downloaded as CSV like every list.
    """
    filters = {
        "user": request.GET.get("user", ""),
        "type": request.GET.get("type", ""),
        "object": request.GET.get("object", "").strip(),
        "action": request.GET.get("action", ""),
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "q": request.GET.get("q", "").strip(),
    }
    since = parse_date(filters["since"]) if filters["since"] else None
    until = parse_date(filters["until"]) if filters["until"] else None
    kind = filters["type"] if filters["type"] in AccessKind.values else ""
    entries = access_log.filtered_entries(
        user=int(filters["user"]) if filters["user"].isdigit() else None,
        kind=kind,
        object_id=filters["object"] if kind else "",
        action=filters["action"] if filters["action"] in AccessAction.values else "",
        since=start_of_day(since) if since else None,
        until=end_of_day(until) if until else None,
        text=filters["q"],
    )
    table = access_log.ACCESS_LOG_TABLE.state(request)
    entries = table.order(entries)
    if table.wants_csv:
        return table.csv_response(entries, _("Access log"))
    page = paginate(request, entries)
    chosen_object = None
    if kind and filters["object"]:
        chosen_object = (
            AccessLogEntry.objects.filter(object_type=kind, object_id=filters["object"])
            .values_list("label", flat=True)
            .first()
        ) or filters["object"]
    without_object = request.GET.copy()
    for name in ("object", "page"):
        without_object.pop(name, None)
    return render(
        request,
        "core/access_log.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "filters": filters,
            "kinds": AccessKind.choices,
            "actions": AccessAction.choices,
            "users": User.objects.order_by("username"),
            "chosen_object": chosen_object,
            "without_object": without_object.urlencode(),
            "retention_days": SystemSettings.load().retention_access_log_days,
        },
    )


def _own_backups(request: HttpRequest) -> list[tuple[BackgroundJob, str | None]]:
    """The backups this user made in the browser, newest first, each with its key if it is encrypted."""
    jobs = BackgroundJob.objects.filter(kind="backup", created_by=request.user)[:10]
    return [(job, backup.key_of(job)) for job in jobs]


@module_required(Module.ADMINISTRATION)
def backup_page(request: HttpRequest) -> HttpResponse:
    """Backup and encryption (ADM-009, ADM-010).

    Shows the last nightly backup, offers a backup for download to those who
    may delete in the settings (like the full export), and says what is
    encrypted – and how to switch encryption on, which only root can do on
    the server. IMP-006: the readable export of all data
    (IMP-006) is a section of this page, with a paragraph on how it differs
    from a backup.
    """
    may_back_up = request_rights(request).can_delete(Module.ADMINISTRATION)
    return render(
        request,
        "core/backup.html",
        {
            "state": backup.encryption_state(),
            "last_backup": backup.last_server_backup(),
            "may_back_up": may_back_up,
            "backups": _own_backups(request) if may_back_up else [],
            "running": backup.running_backup(),
            "retention_days": SystemSettings.load().retention_jobs_days,
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def backup_start(request: HttpRequest) -> HttpResponse:
    """Start a backup in the background (ADM-010); the page shows how far it got."""
    try:
        backup.start(request.user)
    except backup.BackupError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request, _("The backup is being written. You can go on working; you will be told when it is ready.")
        )
    return redirect("core:backup")


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def full_export(request: HttpRequest) -> HttpResponse:
    """Start the full export of all data (IMP-006); the task page offers the download when it is done.

    IMP-006: a section of the page "Sicherung".
    The same right as for a backup: it holds the data of everybody.
    """
    from rentalars.core import export

    job = export.start(request.user)
    return redirect("core:job", pk=job.pk)


@module_required(Module.ADMINISTRATION, Level.DELETE)
def backup_job(request: HttpRequest, pk: int) -> HttpResponse:
    """One own backup as a part of the page – asked for again every two seconds while it is written."""
    job = get_object_or_404(BackgroundJob, pk=pk, kind="backup")
    if job.created_by_id != request.user.pk:
        raise Http404
    context: dict[str, Any] = {"job": job, "key": backup.key_of(job)}
    return render(request, "core/_backup_job.html", context)
