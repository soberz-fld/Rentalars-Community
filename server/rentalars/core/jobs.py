# SPDX-License-Identifier: GPL-3.0-or-later
"""Tasks in the background: large imports, many labels, the full export (NFA-041).

Rentalars has no job queue and no second service (NFA-028). A task that would
keep a page waiting for more than a few seconds is stored as a
:class:`~rentalars.core.models.BackgroundJob` and started at once as a
process of its own (``manage.py run_jobs --job N``). The page that started it
shows its progress and, when done, the download. Whoever started it gets a
notification as well (UIX-005).

If the process could not be started, the timer that runs every minute
(``rentalars-jobs.timer``, see ``deploy/systemd``) runs what is still
waiting. A task whose process ended without finishing – a restart, a crash –
is started once more by the same timer; a second interruption marks it as
failed. Each task records which process runs it, so that this is noticed
within a minute; for a task on another machine the limit is
:data:`STALE_AFTER`.

The kinds of tasks are registered by the modules that know how to do them::

    register("labels", "rentalars.material.labels:run_job")

A kind may have a *gate* (NFA-076): a context manager that
says whether a task of the kind may run now – the conversion of chat videos
runs one at a time on a server. A task that may not stays waiting and its
process ends; the process holding the gate runs the waiting tasks of the
kind one after the other before it lets go, and the timer runs what is left
(a crash lets go of the gate, see ``chat.media.conversion_slot``). Kinds
without a gate run as before.

A runner is called with the job and returns ``(bytes, file name)`` for a
download – or ``(path, file name)`` for a large result written to a
temporary file, which is moved into place – or a text for the result
message. It may set ``job.result`` to keep data such as a report. It may call
:func:`report_progress` along the way. An exception marks the job as failed
with the error as message.
"""

from __future__ import annotations

import datetime
import importlib
import logging
import os
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.i18n import for_user
from rentalars.core.models import BackgroundJob, JobStatus

logger = logging.getLogger(__name__)

#: kind → "module:function"
_RUNNERS: dict[str, str] = {}
#: kind → "module:function" of its gate, a context manager yielding whether a task of the kind may run now.
_GATES: dict[str, str] = {}

#: A task still "running" after this long is taken to be lost (killed with a restart).
STALE_AFTER = datetime.timedelta(hours=2)


def register(kind: str, runner: str, *, gate: str | None = None) -> None:
    """Make a kind of task known; ``runner`` and ``gate`` are ``"dotted.module:function"``."""
    _RUNNERS[kind] = runner
    if gate:
        _GATES[kind] = gate
    else:
        _GATES.pop(kind, None)


def _load(target: str) -> Any:
    module_name, function_name = target.split(":", 1)
    return getattr(importlib.import_module(module_name), function_name)


def _runner(kind: str) -> Callable[[BackgroundJob], Any]:
    target = _RUNNERS.get(kind)
    if target is None:
        raise LookupError(f"Unknown kind of background task: {kind}")
    return _load(target)


def start_job(kind: str, params: dict[str, Any], *, user: Any, title: str) -> BackgroundJob:
    """Store a task and start it as a process of its own once the transaction is committed."""
    if kind not in _RUNNERS:
        raise LookupError(f"Unknown kind of background task: {kind}")
    job = BackgroundJob.objects.create(kind=kind, params=params, title=title[:200], created_by=user)
    if getattr(settings, "JOBS_RUN_INLINE", False):
        # Tests: at once, in this request, so that the test sees the result.
        run_job(job.pk)
        job.refresh_from_db()
    else:
        transaction.on_commit(lambda: _spawn(job.pk))
    return job


def _spawn(job_id: int) -> None:
    """Start ``manage.py run_jobs --job N`` detached from the web worker."""
    command = [sys.executable, str(settings.BASE_DIR / "manage.py"), "run_jobs", "--job", str(job_id)]
    try:
        # Output goes where the output of the application goes – the journal of the service.
        subprocess.Popen(  # noqa: S603 - our own command with a number as argument
            command,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError:
        # The timer picks it up within a minute.
        logger.warning("Background task %s could not be started at once; the timer will run it.", job_id)


def report_progress(job: BackgroundJob, percent: int, message: str = "") -> None:
    """Note how far a task got, for the page that shows it."""
    job.progress = max(0, min(100, int(percent)))
    if message:
        job.message = message[:2000]
    BackgroundJob.objects.filter(pk=job.pk).update(progress=job.progress, message=job.message)


def _claim(job_id: int) -> BackgroundJob | None:
    """Mark a waiting task as running in this process; ``None`` if it is not waiting (any more)."""
    claimed = BackgroundJob.objects.filter(pk=job_id, status=JobStatus.QUEUED).update(
        status=JobStatus.RUNNING, started_at=timezone.now()
    )
    return BackgroundJob.objects.get(pk=job_id) if claimed else None


def _claim_next(kind: str) -> BackgroundJob | None:
    """Claim the oldest waiting task of a kind; ``None`` if none is waiting."""
    waiting = BackgroundJob.objects.filter(kind=kind, status=JobStatus.QUEUED).order_by("created_at", "pk")
    while (job_id := waiting.values_list("pk", flat=True).first()) is not None:
        job = _claim(job_id)
        if job is not None:
            return job
    return None


def run_job(job_id: int) -> BackgroundJob | None:
    """Run one waiting task; ``None`` if it is not waiting (any more) – or waits for the gate of its kind."""
    job = _claim(job_id)
    if job is None:
        return None
    gate = _GATES.get(job.kind)
    if gate is not None:
        return _run_gated(job, gate)
    return _execute(job)


def _run_gated(job: BackgroundJob, gate: str) -> BackgroundJob | None:
    """Run a task of a kind with a gate, then the other waiting ones of the kind (NFA-076).

    Without the gate the task waits again – the process holding the gate, or
    the timer, runs it. A task queued just while the holder lets go is taken
    by trying once more.
    """
    first: BackgroundJob | None = None
    current: BackgroundJob | None = job
    while current is not None:
        with _load(gate)() as may_run:
            if not may_run:
                BackgroundJob.objects.filter(pk=current.pk, status=JobStatus.RUNNING).update(
                    status=JobStatus.QUEUED, started_at=None
                )
                return first
            while current is not None:
                finished = _execute(current)
                first = first or finished
                current = _claim_next(job.kind)
        current = _claim_next(job.kind)
    return first


def _execute(job: BackgroundJob) -> BackgroundJob:
    """Run a claimed task and note how it ended."""
    # Which process runs it: the timer sees from this whether a restart interrupted it.
    job.params = {**job.params, "worker": {"host": socket.gethostname(), "pid": os.getpid()}}
    BackgroundJob.objects.filter(pk=job.pk).update(params=job.params)
    from rentalars.core.audit import acting_as

    try:
        # The change log names the one who started the task, not the timer. UIX-029: what the task writes –
        # its messages, a PDF, a CSV – is in that user's language.
        with acting_as(job.created_by or "system:jobs"), for_user(job.created_by):
            result = _runner(job.kind)(job)
    except Exception as error:
        logger.exception("Background task %s (%s) failed.", job.pk, job.kind)
        job.status = JobStatus.FAILED
        with for_user(job.created_by):
            job.message = _("The task failed: %(error)s") % {"error": error}
    else:
        job.status = JobStatus.DONE
        job.progress = 100
        if isinstance(result, tuple):
            content, name = result
            job.result_name = name[:200]
            if isinstance(content, Path):
                # A large result written to a temporary file (the full export) is not read into memory.
                with content.open("rb") as handle:
                    job.result_file.save(name, File(handle), save=False)
                content.unlink(missing_ok=True)
            else:
                job.result_file.save(name, ContentFile(content), save=False)
        elif result:
            job.message = str(result)[:2000]
    job.finished_at = timezone.now()
    job.save()
    _announce(job)
    return job


def _was_interrupted(job: BackgroundJob) -> bool:
    """Whether a running task lost its process – a restart or a crash killed it."""
    worker = job.params.get("worker") or {}
    if worker.get("host") == socket.gethostname() and worker.get("pid"):
        try:
            os.kill(int(worker["pid"]), 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False
    return job.started_at is not None and job.started_at < timezone.now() - STALE_AFTER


def recover_interrupted_jobs() -> int:
    """Start interrupted tasks once more; a second interruption fails them. Returns how many were found.

    Every kind of task can simply run again: an import writes all or nothing,
    labels and the export make their file anew.
    """
    count = 0
    for job in BackgroundJob.objects.filter(status=JobStatus.RUNNING):
        if not _was_interrupted(job):
            continue
        count += 1
        attempts = int(job.params.get("attempts", 0)) + 1
        params = {**job.params, "attempts": attempts}
        params.pop("worker", None)
        if attempts < 2:
            BackgroundJob.objects.filter(pk=job.pk, status=JobStatus.RUNNING).update(
                status=JobStatus.QUEUED, started_at=None, progress=0, params=params
            )
        else:
            BackgroundJob.objects.filter(pk=job.pk, status=JobStatus.RUNNING).update(
                status=JobStatus.FAILED,
                finished_at=timezone.now(),
                params=params,
                message=_("The task was interrupted."),
            )
    return count


def run_waiting_jobs() -> int:
    """Run every task that is still waiting, after starting interrupted ones again. Returns how many ran."""
    recover_interrupted_jobs()
    count = 0
    for job_id in (
        BackgroundJob.objects.filter(status=JobStatus.QUEUED).order_by("created_at").values_list("pk", flat=True)
    ):
        if run_job(job_id) is not None:
            count += 1
    return count


def _announce(job: BackgroundJob) -> None:
    """Tell the one who started the task that it is finished (UIX-005)."""
    if job.created_by is None:
        return
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    with for_user(job.created_by):  # UIX-029
        title = (
            _("Ready: %(task)s") % {"task": job.title}
            if job.status == JobStatus.DONE
            else _("Failed: %(task)s") % {"task": job.title}
        )
    notify([job.created_by], Kind.JOB_FINISHED, title, body=job.message[:500], url=reverse("core:job", args=[job.pk]))


def delete_old_jobs(days: int | None = None) -> int:
    """Remove finished tasks and their files after the retention period (NFA-011)."""
    from rentalars.core.models import SystemSettings

    days = days if days is not None else SystemSettings.load().retention_jobs_days
    limit = timezone.now() - datetime.timedelta(days=days)
    count = 0
    for job in BackgroundJob.objects.filter(finished_at__lt=limit):
        if job.result_file:
            job.result_file.delete(save=False)
        job.delete()
        count += 1
    return count
