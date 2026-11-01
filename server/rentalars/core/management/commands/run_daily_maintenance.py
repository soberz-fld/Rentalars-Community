# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``run_daily_maintenance``: small clean-up jobs, started once a day (NFA-036).

A systemd timer runs this command; no separate job server is needed.
"""

from __future__ import annotations

from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from rentalars.accounts.models import UserSession
from rentalars.accounts.services import (
    deactivate_expired_accounts,
    delete_old_login_attempts,
    delete_old_security_events,
)
from rentalars.mail.services import delete_old_mail_log_entries, delete_old_mails
from rentalars.notifications.services import delete_old_notifications


class Command(BaseCommand):
    """Clean-up jobs and the nightly reports (without the shortages, VFG-036)."""

    help = (
        "Removes expired sessions, old login attempts, notifications and mails past their retention; "
        "deactivates expired accounts; reports low stock, due inspections, expiring "
        "qualifications and problems of the self-check."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run all jobs; each reports one line."""
        call_command("clearsessions")
        # Sessions Django removed (or that ended otherwise) leave their rows behind (AUT-008).
        from django.contrib.sessions.models import Session

        live = Session.objects.filter(expire_date__gt=timezone.now()).values("session_key")
        UserSession.objects.filter(~Q(session_key__in=live)).delete()
        self.stdout.write(f"Deleted {delete_old_login_attempts()} old login attempts.")
        self.stdout.write(
            f"Deleted {delete_old_security_events()} security log entries past their retention (NFA-011)."
        )
        from rentalars.api.safeguards import delete_old_call_counts
        from rentalars.core.audit import delete_old_entries

        self.stdout.write(f"Deleted {delete_old_entries()} change log entries past their retention (NFA-011).")
        from rentalars.core import access_log

        self.stdout.write(
            f"Deleted {access_log.delete_old_entries()} access log entries past their retention (AUT-028)."
        )
        self.stdout.write(f"Deleted {delete_old_call_counts()} old API call counts and stored answers (API-010).")
        from rentalars.api.webhooks import delete_old_deliveries

        self.stdout.write(f"Deleted {delete_old_deliveries()} webhook deliveries past their retention (API-012).")
        self.stdout.write(f"Deactivated {deactivate_expired_accounts()} expired accounts (AUT-024).")
        from rentalars.accounts.ldap_sync import sync_nightly

        self.stdout.write(sync_nightly() + " (AUT-029)")  # Only if "compare the accounts every night" is on
        from rentalars.core.files import purge_deleted

        self.stdout.write(f"Removed {purge_deleted()} days of deleted files for good (consistent backup).")
        self.stdout.write(f"Deleted {delete_old_notifications()} old notifications.")
        self.stdout.write(f"Deleted {delete_old_mails()} mails past their retention period (EML-031).")
        self.stdout.write(f"Deleted {delete_old_mail_log_entries()} mail log entries past their retention (EML-039).")
        from rentalars.automations.engine import delete_old_runs

        self.stdout.write(f"Deleted {delete_old_runs()} runs of automations past their retention (ADM-013).")
        # VFG-036: shortages are checked by the minute timer (run_jobs) at the time of
        # Einstellungen → Benachrichtigungen, no longer here.
        from rentalars.core.jobs import delete_old_jobs
        from rentalars.material.inspections import report_due_inspections
        from rentalars.material.services import check_low_stock
        from rentalars.personnel.services import check_expiring_qualifications

        self.stdout.write(f"Reported {check_low_stock()} products below their minimum stock (PRD-020).")
        self.stdout.write(f"Reported {report_due_inspections()} inspections that became due (MAT-032).")
        self.stdout.write(f"Reported {check_expiring_qualifications()} expiring qualifications (PER-014).")
        self.stdout.write(f"Deleted {delete_old_jobs()} finished background tasks with their files (NFA-041).")
        from rentalars.core.imports import delete_old_uploads

        self.stdout.write(f"Deleted {delete_old_uploads()} files of imports that were not finished (IMP-001).")
        from rentalars.material.purchases import delete_old_invoices

        # MAT-061: an invoice uploaded for "Kauf einpflegen", never saved; until then only the next upload removed it.
        self.stdout.write(f"Deleted {delete_old_invoices()} invoices of purchases that were never saved.")
        from rentalars.chat.media import delete_old_sources

        # UIX-049, NFA-076: videos left waiting by a crash; until then only the next upload removed them.
        self.stdout.write(f"Deleted {delete_old_sources()} chat videos left waiting for their conversion.")
        from rentalars.core.maps import delete_unused_positions

        self.stdout.write(f"Deleted {delete_unused_positions()} map positions of addresses no longer used (UIX-034).")
        from rentalars.documents import archive
        from rentalars.documents.bookkeeping import bookkeeping_on

        # DOK-043: vouchers get into the archive, a part of the archive is checked against its checksums.
        # Not while Rentalars is not used as accounting software (DOK-055) – no register, no findings.
        if bookkeeping_on():
            archived = archive.run()
            self.stdout.write(
                f"Archived {archived.registered} vouchers, checked {archived.checked} files of the archive, "
                f"{archived.problems} findings (DOK-043)."
            )
        else:
            self.stdout.write("Archive skipped: Rentalars is not used as accounting software (DOK-055).")
        # After the nightly backup: a backup that failed, a full disk … reach the operators (NFA-018).
        from rentalars.core.selfcheck import report_problems

        self.stdout.write(f"Reported {report_problems()} problems of the self-check (NFA-037).")
