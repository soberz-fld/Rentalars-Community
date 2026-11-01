# SPDX-License-Identifier: GPL-3.0-or-later
"""Automatic AI summaries, every night, of projects and service cases that changed (EML-056, NFA-079).

The requirement: projects and service cases whose correspondence changed since their last summary are summarised
automatically, for example every night. This module is the second door to the same logic as the button "Zusammenfassen"
(:mod:`rentalars.ai.summary`): the texts are read and cleaned by :func:`rentalars.ai.summary.prepare_texts`, the
model is asked by :func:`rentalars.ai.summary.summarise`, the result is kept by
:func:`rentalars.ai.summary.store_summary`. What is added here is the choice of *what* to summarise, *when*, and
the brakes.

**Off until an administrator opts in.** ``AISettings.auto_enabled`` is false in a new installation, and switching
it on records who agreed, when and for which provider. If the provider of the summaries changes later – another
server, or from local to a cloud service – the consent no longer holds and the job stops until it is given again
(:func:`consent_holds`). No call to a model is made without it.

**What counts as a change.** A summary is made from the correspondence of a project (mails, notes and, if the
administrator wants it, the chat), so only the correspondence can make it out of date: the number of mails, the
newest mail and the newest chat message are compared with those the stored summary was made from (the same marks the
page uses for "out of date", :func:`rentalars.ai.summary.shown_summary`). Planning lines, tasks, times and documents
are not in the text the model gets; a change there does not make a summary old and does not cost a call. When the
marks differ, the texts are built and hashed: if they equal the ones of the stored summary (a mail with lock the job
may not read arrived), the marks are updated and no model is called.

**The principal.** The job has no user. It acts as the principal ``system:ai-summaries`` with a scope fixed by the
settings (:func:`rentalars.ai.summary.automatic_scope`): by default the mails and notes of the project and of its
parts, messages with lock included (in projects every message starts with the lock; the page shows the summary only
to who reads all messages), not the chat, with the same removals of data classes as every summary. An administrator
can narrow it to the open messages. Whoever sees the stored summary is decided by the rights on the page, as for a
summary by hand.

**Brakes.** A window of the night; at most N summaries per night; a budget of tokens per night; a least time
between two summaries of a project; a least number of mails; only projects in the chosen statuses; a switch per
project and per customer; and a stop after three failures in a row (the provider is down). One run at a time: a row
of :class:`~rentalars.ai.models.AutoSummaryRun` with a unique ``lock`` that a heartbeat keeps alive.

**Failures** never break the job: a project that fails is noted with the error (no mail content), the next one is
tried, and the project is a candidate again the next night. The administrators see every run on the page
"Automatische Zusammenfassungen" and in the API.
"""

from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from rentalars.ai import correspondence, summary
from rentalars.ai import speed as speeds
from rentalars.ai.client import AIError, Endpoint, endpoint_for
from rentalars.ai.models import (
    AICall,
    AISettings,
    AISummary,
    AISummaryVersion,
    AutoSummaryExclusion,
    AutoSummaryRun,
    RunState,
    Use,
    address_origin,
)
from rentalars.core.audit import acting_as
from rentalars.mail.models import ProjectMail
from rentalars.projects.models import Project, ProjectKind

logger = logging.getLogger(__name__)

#: The name the changes of the job are logged under.
PRINCIPAL = "system:ai-summaries"
#: A run that did not report for this long is taken to be dead; it no longer blocks the next one.
LOCK_SECONDS = 7200
#: After this many failed projects in a row the job gives up for the night: the provider is probably down.
MAX_FAILURES_IN_A_ROW = 3
#: A night whose run could not reach the provider is tried again, at most this many times and this far apart.
MAX_ATTEMPTS = 3
RETRY_AFTER = datetime.timedelta(minutes=20)
#: Runs older than this are removed (the log is for the administrators, not an archive).
KEEP_RUNS_DAYS = 180
#: The most entries ``AutoSummaryRun.details`` keeps.
MAX_DETAILS = 200
#: How long the heartbeat waits between two writes, in seconds.
HEARTBEAT_EVERY = 20.0
#: How far past the end of the window a summary begun in time may run (minutes).
GRACE_MINUTES = 10


# --- The window of the night -------------------------------------------------------------------------------


def in_window(moment: datetime.datetime, ai_settings: AISettings | None = None) -> bool:
    """Whether ``moment`` (local time) lies in the window of the night; a window may cross midnight."""
    ai_settings = ai_settings or AISettings.load()
    start, end, now = ai_settings.auto_window_start, ai_settings.auto_window_end, moment.time()
    if start == end:
        return True
    return start <= now < end if start < end else (now >= start or now < end)


def night_of(moment: datetime.datetime, ai_settings: AISettings | None = None) -> datetime.date:
    """The day the window of the night began on – the name of the night; one run is made per night."""
    ai_settings = ai_settings or AISettings.load()
    if ai_settings.auto_window_start > ai_settings.auto_window_end and moment.time() < ai_settings.auto_window_end:
        return moment.date() - datetime.timedelta(days=1)
    return moment.date()


def window_ends_at(moment: datetime.datetime, ai_settings: AISettings) -> datetime.datetime:
    """When the window that ``moment`` is in ends (local time)."""
    end = datetime.datetime.combine(moment.date(), ai_settings.auto_window_end, tzinfo=moment.tzinfo)
    if end <= moment:
        end += datetime.timedelta(days=1)
    return end


# --- Consent -----------------------------------------------------------------------------------------------


def consent_key(endpoint: Endpoint) -> str:
    """What the operator agreed to: the local AI, or the server (scheme, host, port) of a provider.

    A provider's model or name may change; where the texts go may not, without a new consent.
    """
    if endpoint.is_local:
        return "local"
    scheme, host, port = address_origin(endpoint.base_url)
    return f"provider:{scheme}://{host}:{port}"


def consent_holds(ai_settings: AISettings, endpoint: Endpoint) -> bool:
    """Whether the opt-in was given for the server the summaries go to now."""
    return bool(ai_settings.auto_enabled and ai_settings.auto_consent_key == consent_key(endpoint))


def switch_on(ai_settings: AISettings, user: Any) -> None:
    """Opt in: record who agreed, when, and for which server (the caller saves).

    Raises:
        AIError: Summaries are switched off or the provider is not usable – there is nothing to agree to.
    """
    endpoint = endpoint_for(Use.SUMMARY)
    ai_settings.auto_enabled = True
    ai_settings.auto_consent_key = consent_key(endpoint)
    ai_settings.auto_enabled_by = user if getattr(user, "pk", None) else None
    ai_settings.auto_enabled_at = timezone.now()


def switch_off(ai_settings: AISettings) -> None:
    """Opt out: no further call (the caller saves)."""
    ai_settings.auto_enabled = False
    ai_settings.auto_consent_key = ""


def consent_state(ai_settings: AISettings) -> str:
    """For the page: ``off``, ``ok``, ``changed`` (another server than agreed) or ``unavailable`` (no usable provider)."""
    if not ai_settings.auto_enabled:
        return "off"
    try:
        endpoint = endpoint_for(Use.SUMMARY)
    except AIError:
        return "unavailable"
    return "ok" if consent_holds(ai_settings, endpoint) else "changed"


# --- Switches per project and per customer -----------------------------------------------------------------


def is_excluded(project: Project) -> bool:
    """Whether the project, or its customer, is excluded from automatic summaries."""
    if AutoSummaryExclusion.objects.filter(project=project).exists():
        return True
    return bool(project.customer_id and AutoSummaryExclusion.objects.filter(customer_id=project.customer_id).exists())


def set_exclusion(*, project: Project | None = None, customer: Any = None, excluded: bool, user: Any) -> None:
    """Switch "no automatic AI summaries" on or off for a project or a customer (audited like any change)."""
    target = {"project": project} if project is not None else {"customer": customer}
    existing = AutoSummaryExclusion.objects.filter(**target).first()
    if excluded and existing is None:
        AutoSummaryExclusion.objects.create(**target, created_by=user if getattr(user, "pk", None) else None)
    elif not excluded and existing is not None:
        existing.delete()


# --- Which projects ------------------------------------------------------------------------------------------


def eligible_projects(ai_settings: AISettings) -> QuerySet[Project]:
    """Projects and service cases in the chosen statuses with correspondence, not excluded, newest mail first."""
    statuses = Q(kind=ProjectKind.PROJECT, status__in=ai_settings.auto_project_statuses or [])
    cases = Q(kind=ProjectKind.SERVICE_CASE, case_status__in=ai_settings.auto_case_statuses or [])
    own = ProjectMail.objects.filter(project_id=OuterRef("pk"))
    in_parts = ProjectMail.objects.filter(project__parent_id=OuterRef("pk"))
    newest = ProjectMail.objects.filter(project_id=OuterRef("pk")).order_by("-date").values("date")[:1]
    return (
        Project.objects.filter(statuses | cases)
        .filter(Exists(own) | Exists(in_parts))
        .exclude(Exists(AutoSummaryExclusion.objects.filter(project_id=OuterRef("pk"))))
        .exclude(Exists(AutoSummaryExclusion.objects.filter(customer_id=OuterRef("customer_id"))))
        .exclude(customer__anonymised_at__isnull=False)
        .annotate(newest_mail=Subquery(newest))
        .select_related("customer")
        .order_by("-newest_mail", "-id")
    )


def project_ids_of(project: Project) -> list[int]:
    """The projects whose correspondence the summary of ``project`` covers: itself and, for a whole project, its parts.

    The job reads all parts: it has no user whose rights would pick some (the page hides a summary from whoever
    may not read every part it covers, as for a summary by hand).
    """
    ids = [project.pk]
    if project.parent_id is None:
        ids += sorted(Project.objects.filter(parent_id=project.pk).values_list("pk", flat=True))
    return ids


@dataclass
class Verdict:
    """What the job would do with one project, and why."""

    action: str  # "summarise", "unchanged", "recent", "too_few"
    # (``mails`` is what the job may read; ``new_mails`` the mails since the stored summary)
    reason: str = ""  # "new" (no summary yet) or "changed"
    mails: int = 0
    new_mails: int = 0
    state: correspondence.State | None = None
    existing: AISummary | None = None
    #: Too few readable mails only because the job may not read messages with lock.
    locked_out: bool = False


def judge(project: Project, ai_settings: AISettings, scope: summary.Scope, *, now: datetime.datetime) -> Verdict:
    """Whether a project needs a new summary: the cheap checks, from the marks of the correspondence (no model, no text)."""
    ids = project_ids_of(project)
    state = correspondence.state_of(ids)
    existing = AISummary.objects.filter(project=project).first()
    # What counts is what the job may read: a project whose messages all have a lock has nothing for it.
    readable = correspondence.readable_count(
        ids, include_notes=scope.include_notes, include_locked=scope.include_locked
    )
    if readable < ai_settings.auto_min_mails:
        locked_out = not scope.include_locked and (
            correspondence.readable_count(ids, include_notes=scope.include_notes, include_locked=True)
            >= ai_settings.auto_min_mails
        )
        return Verdict("too_few", mails=readable, state=state, existing=existing, locked_out=locked_out)
    if existing is None:
        return Verdict("summarise", "new", mails=state.mail_count, new_mails=state.mail_count, state=state)
    changed = state.mail_count != existing.mail_count or state.newest_mail_id != existing.newest_mail_id
    if scope.include_chat and state.newest_chat_id != existing.newest_chat_id:
        changed = True
    if not changed:
        return Verdict("unchanged", mails=state.mail_count, state=state, existing=existing)
    wait = datetime.timedelta(hours=ai_settings.auto_min_interval_hours)
    if existing.created_at > now - wait:
        return Verdict("recent", "changed", mails=state.mail_count, state=state, existing=existing)
    new = max(0, state.mail_count - existing.mail_count)
    return Verdict("summarise", "changed", mails=state.mail_count, new_mails=new, state=state, existing=existing)


# --- The run -----------------------------------------------------------------------------------------------


class _StopError(Exception):
    """The run ends early; ``reason`` says why (budget, limit, window)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def tokens_after(call_id: int) -> int:
    """The tokens the automatic calls after ``call_id`` used – as the server counted, else a third of the characters."""
    total = 0
    rows = AICall.objects.filter(automatic=True, pk__gt=call_id).values_list(
        "prompt_tokens", "completion_tokens", "request_chars", "response_chars"
    )
    for prompt, completion, request_chars, response_chars in rows:
        total += prompt if prompt is not None else request_chars // 3
        total += completion if completion is not None else response_chars // 3
    return total


def _acquire(run: AutoSummaryRun) -> bool:
    """Take the lock: a run row with ``lock = 1``; false if another run is under way."""
    now = timezone.now()
    AutoSummaryRun.objects.filter(lock=1, heartbeat_at__lt=now - datetime.timedelta(seconds=LOCK_SECONDS)).update(
        lock=None, state=RunState.ABORTED, reason="interrupted", finished_at=now
    )
    run.lock = 1
    try:
        with transaction.atomic():
            run.save()
    except IntegrityError:
        return False
    return True


def _forget_old_runs() -> None:
    """Remove runs past :data:`KEEP_RUNS_DAYS`."""
    AutoSummaryRun.objects.filter(started_at__lt=timezone.now() - datetime.timedelta(days=KEEP_RUNS_DAYS)).delete()


def run(
    *,
    dry_run: bool = False,
    ignore_window: bool = False,
    user: Any = None,
    only_project: int | None = None,
    limit: int | None = None,
) -> AutoSummaryRun | None:
    """One run of the nightly job; returns its record, or ``None`` if nothing was done.

    ``None``: the opt-in is missing (not a dry run), or another run holds the lock. A dry run lists what would be
    summarised (``details``, outcome ``would``) and calls no model; its record is not saved.

    Args:
        dry_run: Only list what would be summarised.
        ignore_window: Run now although it is not night – the administrator's "run now" and the command.
        user: Who started it by hand (kept in the record), or ``None`` for the timer.
        only_project: Only this project (testing, the command's ``--project``).
        limit: At most this many summaries (otherwise the setting).
    """
    ai_settings = AISettings.load()
    now = timezone.localtime()
    run_record = AutoSummaryRun(
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
        dry_run=dry_run,
        night=night_of(now, ai_settings),
        triggered_by=user if getattr(user, "pk", None) else None,
        state=RunState.DRY_RUN if dry_run else RunState.RUNNING,
    )
    if not dry_run and not ai_settings.auto_enabled:
        return None
    if not dry_run:
        _forget_old_runs()
        if not _acquire(run_record):
            logger.info("Automatic summaries: another run is under way.")
            return None
    try:
        endpoint = endpoint_for(Use.SUMMARY)
        if not dry_run and not consent_holds(ai_settings, endpoint):
            # Review: the night counts as done, or the timer would start a new run every few minutes all night.
            _finish(run_record, RunState.STOPPED, reason="consent")
            _note_night(run_record, ai_settings, now)
            return run_record
        _loop(
            run_record,
            ai_settings,
            endpoint,
            now=now,
            ignore_window=ignore_window,
            only_project=only_project,
            limit=limit,
        )
    except AIError as error:
        run_record.details = [*run_record.details, {"outcome": "failed", "error": str(error)[:300]}]
        _finish(run_record, RunState.FAILED, reason="provider")
    except _StopError as stop:
        _finish(run_record, RunState.STOPPED, reason=stop.reason)
    except Exception:
        logger.exception("Automatic summaries failed.")
        run_record.details = [*run_record.details, {"outcome": "failed", "error": "unexpected error, see the log"}]
        _finish(run_record, RunState.FAILED, reason="error")
    else:
        final = RunState.STOPPED if run_record.state == RunState.STOPPED else RunState.DONE
        _finish(run_record, RunState.DRY_RUN if dry_run else final, reason=run_record.reason)
    _note_night(run_record, ai_settings, now)
    return run_record


def _finish(run_record: AutoSummaryRun, state: str, *, reason: str = "") -> AutoSummaryRun:
    """Close the record: state, reason, end, and let go of the lock."""
    run_record.state = state
    run_record.reason = reason
    run_record.finished_at = timezone.now()
    run_record.details = run_record.details[:MAX_DETAILS]
    run_record.lock = None
    if not run_record.dry_run:
        run_record.save()
    return run_record


def _note_night(run_record: AutoSummaryRun, ai_settings: AISettings, now: datetime.datetime) -> None:
    """Remember that this night is done, unless the provider could not be reached (then it is tried again, a few times)."""
    if run_record.dry_run or not in_window(now, ai_settings):
        return
    night = night_of(now, ai_settings)
    tries = AutoSummaryRun.objects.filter(night=night, dry_run=False).count()
    failed_everywhere = run_record.reason == "provider" or (run_record.failed and not run_record.summarised)
    if failed_everywhere and not run_record.summarised and tries < MAX_ATTEMPTS:
        return
    AISettings.objects.filter(pk=1).update(auto_last_night=night)


def _loop(
    run_record: AutoSummaryRun,
    ai_settings: AISettings,
    endpoint: Endpoint,
    *,
    now: datetime.datetime,
    ignore_window: bool,
    only_project: int | None,
    limit: int | None,
) -> None:
    """Go through the projects: judge, and summarise those that changed – until a brake holds."""
    scope = summary.automatic_scope(ai_settings)
    cap = limit or ai_settings.auto_max_per_run
    budget = ai_settings.auto_token_budget
    window_end = None if ignore_window else window_ends_at(now, ai_settings)
    last_call = AICall.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
    failures_in_a_row = 0
    only_locked = 0
    beat = [time.monotonic()]
    projects = eligible_projects(ai_settings)
    if only_project:
        projects = projects.filter(pk=only_project)
    for project in projects.iterator(chunk_size=200):
        moment = timezone.localtime()
        verdict = judge(project, ai_settings, scope, now=timezone.now())
        if verdict.action == "unchanged" or verdict.action == "recent":
            continue
        if verdict.action == "too_few":
            only_locked += bool(verdict.locked_out)
            continue
        run_record.candidates += 1
        if run_record.dry_run:
            if len(run_record.details) < MAX_DETAILS:
                run_record.details.append(
                    {
                        "project": project.pk,
                        "number": project.number,
                        "name": project.name,
                        "outcome": "would",
                        "reason": verdict.reason,
                        "mails": verdict.mails,
                        "new_mails": verdict.new_mails,
                    }
                )
            continue
        # The brakes: the cap of the night, the window, the budget – a project that is left over waits for tomorrow.
        if run_record.summarised >= cap:
            run_record.reason = "limit"
            break
        if window_end is not None and moment >= window_end:
            run_record.reason = "window"
            break
        used = tokens_after(last_call)
        run_record.tokens = used
        if budget and used >= budget:
            run_record.reason = "budget"
            break
        try:
            outcome = _summarise_one(
                project,
                ai_settings,
                endpoint,
                scope,
                verdict,
                run_record=run_record,
                budget_left=(budget - used) if budget else None,
                window_end=window_end,
                beat=beat,
            )
        except _StopError as stop:
            run_record.reason = stop.reason
            break
        except AIError as error:
            failures_in_a_row += 1
            run_record.failed += 1
            run_record.details.append(
                {"project": project.pk, "number": project.number, "outcome": "failed", "error": str(error)[:300]}
            )
            _heartbeat(run_record, beat, force=True)
            if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                run_record.reason = "provider"
                break
            continue
        except Exception:
            # One project must not stop the night: the next one is tried, this one again tomorrow.
            logger.exception("Automatic summary of project %s failed.", project.pk)
            failures_in_a_row += 1
            run_record.failed += 1
            run_record.details.append(
                {"project": project.pk, "number": project.number, "outcome": "failed", "error": "unexpected error"}
            )
            if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                run_record.reason = "provider"
                break
            continue
        failures_in_a_row = 0
        if outcome == "summarised":
            run_record.summarised += 1
        elif outcome == "unchanged":
            run_record.unchanged += 1
        if len(run_record.details) < MAX_DETAILS:
            run_record.details.append({"project": project.pk, "number": project.number, "outcome": outcome})
        run_record.tokens = tokens_after(last_call)
        _heartbeat(run_record, beat, force=True)
    if only_locked:
        # The administrator should know why projects with mails get nothing: the scope leaves messages with lock out.
        run_record.details.append({"outcome": "only_locked", "count": only_locked})
    if not run_record.dry_run:
        run_record.tokens = tokens_after(last_call)
        if run_record.reason in {"window", "budget", "limit", "provider"}:
            run_record.state = RunState.STOPPED


def _heartbeat(run_record: AutoSummaryRun, beat: list[float], *, force: bool = False) -> None:
    """Tell the lock that the run lives, and save how far it got – at most every :data:`HEARTBEAT_EVERY` seconds."""
    if run_record.dry_run or run_record.pk is None:
        return
    moment = time.monotonic()
    if not force and moment - beat[0] < HEARTBEAT_EVERY:
        return
    beat[0] = moment
    AutoSummaryRun.objects.filter(pk=run_record.pk).update(
        heartbeat_at=timezone.now(),
        candidates=run_record.candidates,
        summarised=run_record.summarised,
        unchanged=run_record.unchanged,
        failed=run_record.failed,
        tokens=run_record.tokens,
    )


def _summarise_one(
    project: Project,
    ai_settings: AISettings,
    endpoint: Endpoint,
    scope: summary.Scope,
    verdict: Verdict,
    *,
    run_record: AutoSummaryRun,
    budget_left: int | None,
    window_end: datetime.datetime | None,
    beat: list[float],
) -> str:
    """Make the summary of one project through the same path as the button; returns the outcome.

    ``summarised``, ``unchanged`` (the texts are those of the stored summary), ``empty`` or ``too_big`` (alone more
    than the budget of the night).
    """
    existing = verdict.existing
    language = existing.language if existing and existing.language in summary.LANGUAGE_NAMES else "de"
    project_ids = project_ids_of(project)
    state = verdict.state or correspondence.state_of(project_ids)
    prepared = summary.prepare_texts(project_ids, scope, language=language)
    if not prepared.texts:
        return "empty"
    if existing is not None and existing.input_hash and existing.input_hash == prepared.input_hash:
        # What the job may read did not change (e.g. a message with lock): note the marks, call no model.
        AISummary.objects.filter(pk=existing.pk).update(
            mail_count=state.mail_count,
            newest_mail_id=state.newest_mail_id,
            newest_mail_date=state.newest_mail_date,
            newest_chat_id=state.newest_chat_id if existing.include_chat else existing.newest_chat_id,
        )
        return "unchanged"
    plan = summary.plan_of(prepared.texts, endpoint)
    expected = plan.prompt_tokens + plan.upper_answer_tokens
    if budget_left is not None and expected > ai_settings.auto_token_budget:
        return "too_big"
    if budget_left is not None and expected > budget_left:
        raise _StopError("budget")
    found = summary.estimate_of(prepared.texts, endpoint)
    deadline = time.monotonic() + speeds.limit_of(found)
    if window_end is not None:
        seconds_left = (window_end - timezone.localtime()).total_seconds() + GRACE_MINUTES * 60
        deadline = min(deadline, time.monotonic() + max(60.0, seconds_left))

    def alive(_percent: int, _message: str) -> None:
        _heartbeat(run_record, beat)

    with acting_as(PRINCIPAL), translation.override(language):
        result = summary.summarise(
            prepared.texts,
            project_name=f"{project.number} {project.name}",
            endpoint=endpoint,
            language=language,
            user=None,
            project=project,
            progress=alive,
            deadline=deadline,
            automatic=True,
        )
        summary.store_summary(
            project,
            result=result,
            endpoint=endpoint,
            language=language,
            state=state,
            scope=scope,
            prepared=prepared,
            project_ids=project_ids,
            user=None,
        )
    return "summarised"


# --- The timer and the task --------------------------------------------------------------------------------


def run_due() -> Any:
    """Start the night's run if it is due (the minute timer, ``run_jobs``); the task is a background task of its own.

    Due: the opt-in is given, it is night (the window), no run was made this night yet (or the provider could not be
    reached and the last attempt is long enough ago), and no such task is waiting or running. A minute without a due run
    costs one query.
    """
    from rentalars.core.jobs import start_job
    from rentalars.core.models import BackgroundJob, JobStatus

    ai_settings = AISettings.load()
    if not ai_settings.auto_enabled:
        return None
    now = timezone.localtime()
    if not in_window(now, ai_settings):
        return None
    night = night_of(now, ai_settings)
    if ai_settings.auto_last_night == night:
        return None
    last = AutoSummaryRun.objects.filter(night=night, dry_run=False).order_by("-started_at").first()
    if last is not None:
        if last.state == RunState.RUNNING or (last.finished_at and last.finished_at > timezone.now() - RETRY_AFTER):
            return None
    if BackgroundJob.objects.filter(
        kind="ai_auto_summaries", status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
    ).exists():
        return None
    return start_job("ai_auto_summaries", {"night": night.isoformat()}, user=None, title=_("Automatic AI summaries"))


def run_job(job: Any) -> str:
    """The background task: one run; the message says what it did."""
    manual = bool(job.params.get("now"))  # "Run now" on the settings page: outside the window, started by a person
    record = run(ignore_window=manual, user=job.created_by if manual else None)
    if record is None:
        return _("Nothing to do: automatic summaries are off or another run is under way.")
    return describe(record)


def describe(record: AutoSummaryRun) -> str:
    """One sentence on a run, for the task and the command."""
    text = _("%(done)s summarised, %(same)s unchanged, %(failed)s failed, %(tokens)s tokens.") % {
        "done": record.summarised,
        "same": record.unchanged,
        "failed": record.failed,
        "tokens": record.tokens,
    }
    if record.reason:
        text += " " + _("Stopped: %(reason)s.") % {"reason": reason_label(record.reason)}
    return text


def reason_label(reason: str) -> str:
    """Why a run ended early, in words."""
    return {
        "budget": _("the token budget of the night is used up"),
        "limit": _("the most summaries per night are made"),
        "window": _("the window of the night is over"),
        "provider": _("the provider could not be reached or kept failing"),
        "consent": _("the provider is not the one that was agreed to – switch the summaries on again"),
        "interrupted": _("the run was interrupted"),
        "error": _("an unexpected error, see the log"),
    }.get(reason, reason)


# --- Erasure -----------------------------------------------------------------------------------------------


def forget_customer(customer: Any) -> int:
    """Delete the summaries of all projects of a customer, and their earlier versions (GDPR erasure).

    A summary carries names, dates and amounts from the correspondence; when a customer's personal data are
    erased it is not regenerated, it goes. Returns how many rows went.
    """
    # A subproject has the customer of its whole project, so the customer's projects are all that carry his data.
    ids = list(customer.projects.values_list("pk", flat=True))
    count = AISummary.objects.filter(project_id__in=ids).delete()[0]
    count += AISummaryVersion.objects.filter(project_id__in=ids).delete()[0]
    return count
