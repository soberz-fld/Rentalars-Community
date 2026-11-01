# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``run_jobs``: run tasks in the background (NFA-041).

Started for one task right after it was created (``--job N``), and every
minute by the timer for whatever is still waiting – and for what is due by the
minute: calendars, webhooks, follow-ups of projects (PRJ-105), waiting runs of
automations (ADM-013), the shortage check at its time (VFG-036), the
reminders of invoices not written yet (DOK-015) and of the times
waiting for approval (ZEI-029).
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from rentalars.core.audit import acting_as
from rentalars.core.jobs import run_job, run_waiting_jobs


def _run_due_calendars() -> None:
    """Read linked calendars and write CalDAV calendars that are due (PER-022, PER-023).

    Rides on the same minute timer; whatever goes wrong there must not stop the tasks.
    """
    try:
        from rentalars.personnel.calendars import run_due

        run_due()
    except Exception:
        logging.getLogger(__name__).exception("The calendars could not be synchronised.")


def _deliver_due_webhooks() -> None:
    """Send the webhook deliveries that are due (API-012); bounded in time, never stops the tasks."""
    try:
        from rentalars.api.webhooks import run_due

        run_due()
    except Exception:
        logging.getLogger(__name__).exception("The webhooks could not be delivered.")


def _notify_due_follow_ups() -> None:
    """Tell the users whose follow-up day has come (PRJ-105); never stops the tasks."""
    try:
        from rentalars.projects.follow_up import notify_due_follow_ups

        notify_due_follow_ups()
    except Exception:
        logging.getLogger(__name__).exception("The follow-ups could not be notified.")


def _run_pending_automations() -> None:
    """Carry out runs of automations that are still waiting, e.g. after a restart (ADM-013); never raises."""
    from rentalars.automations.engine import run_pending

    run_pending()


def _check_shortages_when_due() -> None:
    """VFG-036: the shortage check at the time set under Einstellungen → Benachrichtigungen.

    The time is a setting,
    so it rides on this minute timer, which every installation has: no
    timer of the operating system needs to change. First of the jobs of the
    minute, so that a long task waiting does not delay it; never stops the tasks.
    """
    try:
        from rentalars.notifications.services import run_due_shortage_check

        run_due_shortage_check()
    except Exception:
        logging.getLogger(__name__).exception("The shortages could not be checked.")


def _remind_invoices_when_due() -> None:
    """DOK-015: remind of closed projects without invoice, once a day at the time set; never stops the tasks."""
    try:
        from rentalars.documents.invoice_reminders import run_due_invoice_reminders

        run_due_invoice_reminders()
    except Exception:
        logging.getLogger(__name__).exception("The invoices could not be reminded of.")


def _remind_approvals_when_due() -> None:
    """ZEI-029: remind the approvers of times waiting, once a day at the time set."""
    try:
        from rentalars.timetracking.reminders import run_due_approval_reminders

        run_due_approval_reminders()
    except Exception:
        logging.getLogger(__name__).exception("The times to approve could not be reminded of.")


def _start_auto_summaries_when_due() -> None:
    """Start the night's automatic AI summaries as a task of their own when it is night and they are on.

    Off until an administrator opts in; a minute outside the window costs one query. The task runs as a process
    of its own (``start_job``), so that hours of a slow model do not hold up the tasks of the minute.
    """
    try:
        from rentalars.ai.auto import run_due

        run_due()
    except Exception:
        logging.getLogger(__name__).exception("The automatic AI summaries could not be started.")


class Command(BaseCommand):
    """Run one task, or all waiting ones."""

    help = "Runs tasks in the background: large imports, many labels, the full export."

    def add_arguments(self, parser: CommandParser) -> None:
        """Define the command line options."""
        parser.add_argument("--job", type=int, help="run only this task")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run and report."""
        with acting_as("system:jobs"):
            if options.get("job"):
                job = run_job(options["job"])
                if job is not None and options["verbosity"] > 1:
                    self.stdout.write(f"{job.pk}: {job.get_status_display()}")
                return
            _check_shortages_when_due()  # VFG-036
            _remind_invoices_when_due()  # DOK-015
            _remind_approvals_when_due()  # ZEI-029
            count = run_waiting_jobs()
            _run_due_calendars()
            _deliver_due_webhooks()
            _notify_due_follow_ups()
            _run_pending_automations()
            _start_auto_summaries_when_due()  # last: its task starts as a process of its own
        if count and options["verbosity"] > 0:
            self.stdout.write(f"{count} task run." if count == 1 else f"{count} tasks run.")
